"""Message send endpoints — fully wired to MetaClient.

POST /messages/send/text          — send plain text
POST /messages/send/template      — send approved template
POST /messages/send/mark-read     — mark inbound message as read
GET  /messages/conversations      — list conversations (inbox)
GET  /messages/conversations/{id}/messages — messages in a conversation

MetaClient connection:
  - Built via build_client(access_token, redis) so rate limiter is always active
  - MetaRateLimiter enforces 80 msg/s per phone number (Redis sliding window)
  - MetaAuthError   → 401  (token expired — admin must refresh System User Token)
  - MetaRateLimitError → 429 (too many requests — caller should back off)
  - MetaAPIError    → 502  (other Meta errors)
"""
import hashlib
import json
import mimetypes
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.core.security import decode_token
from app.core.idempotency import IdempotencyKey, check_and_set, clear
from app.core.redis_client import get_redis
from app.integration.meta.deps import build_client
from app.integration.meta.exceptions import MetaAPIError, MetaAuthError, MetaRateLimitError
from app.models.contact import Contact
from app.models.message import (
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
)
from app.models.whatsapp import PhoneNumber, WabaAccount
from app.schemas.messages import (
    ConversationResponse,
    MarkReadRequest,
    MessageResponse,
    SendMessageResponse,
    SendTemplateRequest,
    SendTextRequest,
)
from app.services.billing_service import confirm_credits, reserve_credits, rollback_credits

router = APIRouter(prefix="/messages", tags=["Messages"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]

SESSION_WINDOW_HOURS = 24


# ── Shared helpers ─────────────────────────────────────────────────────────────

async def _get_phone_and_waba(
    db: AsyncSession,
    phone_id: uuid.UUID,
    org_id: uuid.UUID,
) -> tuple[PhoneNumber, WabaAccount]:
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_id,
            PhoneNumber.org_id == org_id,
            PhoneNumber.is_active == True,
        )
    )
    phone = result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found or inactive")

    waba_result = await db.execute(
        select(WabaAccount).where(WabaAccount.id == phone.waba_id)
    )
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")
    return phone, waba


async def _upsert_contact(db: AsyncSession, org_id: uuid.UUID, phone_e164: str) -> Contact:
    result = await db.execute(
        select(Contact).where(Contact.org_id == org_id, Contact.phone == phone_e164)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        contact = Contact(org_id=org_id, phone=phone_e164)
        db.add(contact)
        await db.flush()
    return contact


async def _get_or_create_conversation(
    db: AsyncSession,
    org_id: uuid.UUID,
    contact_id: uuid.UUID,
    phone_number_id: uuid.UUID,
) -> Conversation:
    now = datetime.now(timezone.utc)
    # Always reuse the most recent open conversation for this contact,
    # regardless of session expiry — one thread per contact.
    result = await db.execute(
        select(Conversation).where(
            Conversation.org_id == org_id,
            Conversation.contact_id == contact_id,
            Conversation.phone_number_id == phone_number_id,
            Conversation.status == ConversationStatus.open,
        ).order_by(Conversation.last_message_at.desc().nullslast())
        .limit(1)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        conv = Conversation(
            org_id=org_id,
            contact_id=contact_id,
            phone_number_id=phone_number_id,
            status=ConversationStatus.open,
            session_expires_at=now + timedelta(hours=SESSION_WINDOW_HOURS),
            last_message_at=now,
        )
        db.add(conv)
        await db.flush()
    return conv


def _meta_error_to_http(exc: MetaAPIError) -> HTTPException:
    """Map a Meta exception to the appropriate HTTP error for the caller."""
    if isinstance(exc, MetaAuthError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Meta access token invalid or expired — org admin must refresh the System User Token. ({exc})",
        )
    if isinstance(exc, MetaRateLimitError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Meta rate limit hit — too many messages per second. Retry after 1 second.",
            headers={"Retry-After": "1"},
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Meta API error: {exc}",
    )


async def _get_cost(db, org_id: uuid.UUID, conversation_type: str) -> float:
    from app.services.billing_service import get_credit_rate
    return await get_credit_rate(db, conversation_type, "IN", org_id)


async def _publish(redis, org_id: uuid.UUID, conv_id: uuid.UUID, msg: Message) -> None:
    channel = f"inbox:{org_id}"
    payload = {
        "event": "new_message",
        "conversation_id": str(conv_id),
        "message_id": str(msg.id),
        "direction": msg.direction.value,
        "status": msg.status.value,
        "message_type": msg.message_type,
        "content": msg.content,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
    try:
        await redis.publish(channel, json.dumps(payload))
    except Exception as exc:
        logger.warning("redis.publish_failed", error=str(exc))


# ── Send text ─────────────────────────────────────────────────────────────────

@router.post("/send/text", response_model=SendMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_text_message(
    body: SendTextRequest,
    current_user: CurrentUser,
    db: DbDep,
) -> dict:
    """Send a plain text message.

    - Idempotent: same org+recipient+content within 24h returns 409
    - Two-phase billing: credits reserved before send, confirmed after, rolled back on failure
    - Rate-limited: 80 msg/s per phone number (enforced via Redis)
    """
    redis = await get_redis()
    org_id = current_user.org_id

    # Derive idempotency key
    content_hash = hashlib.sha256(body.body.encode()).hexdigest()[:16]
    idem_key = body.idempotency_key or IdempotencyKey.message(str(org_id), body.to, "", content_hash)
    redis_key = f"idem:msg:{idem_key}"

    if await check_and_set(redis, redis_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate request — this message was already sent.",
        )

    phone, waba = await _get_phone_and_waba(db, body.phone_number_id, org_id)

    # Phase 1 billing: reserve
    cost = await _get_cost(db, org_id, "service")
    txn = None
    if cost > 0:
        txn = await reserve_credits(
            db,
            org_id=org_id,
            amount=cost,
            idempotency_key=IdempotencyKey.wallet_debit(str(org_id), idem_key),
            description=f"Text to {body.to}",
        )
        await db.flush()

    contact = await _upsert_contact(db, org_id, body.to)
    conv = await _get_or_create_conversation(db, org_id, contact.id, phone.id)

    # Send via MetaClient (with rate limiter)
    client = build_client(waba.access_token, redis)
    try:
        result = await client.send_text(
            phone_number_id=phone.phone_number_id,
            to=body.to,
            body=body.body,
        )
    except MetaAPIError as exc:
        if txn:
            await rollback_credits(db, txn)
        await db.commit()
        await clear(redis, redis_key)
        raise _meta_error_to_http(exc)

    now = datetime.now(timezone.utc)
    msg = Message(
        org_id=org_id,
        conversation_id=conv.id,
        wa_message_id=result.wa_message_id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        message_type="text",
        content={"body": body.body},
        cost_credits=cost,
        idempotency_key=idem_key,
        sent_at=now,
        created_at=now,
    )
    db.add(msg)
    conv.last_message_at = now  # type: ignore[assignment]
    conv.session_expires_at = now + timedelta(hours=SESSION_WINDOW_HOURS)  # type: ignore[assignment]

    # Phase 2 billing: confirm
    await db.flush()
    if txn:
        txn.message_id = msg.id  # type: ignore[assignment]
        await confirm_credits(db, txn)

    await db.commit()
    await db.refresh(msg)
    await _publish(redis, org_id, conv.id, msg)

    logger.info("message.text_sent", org_id=str(org_id), wa_id=result.wa_message_id, to=body.to, cost=cost)

    return {
        "message_id": msg.id,
        "wa_message_id": result.wa_message_id,
        "status": msg.status.value,
        "cost_credits": cost,
    }


# ── Send template ─────────────────────────────────────────────────────────────

@router.post("/send/template", response_model=SendMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_template_message(
    body: SendTemplateRequest,
    current_user: CurrentUser,
    db: DbDep,
) -> dict:
    """Send an approved WhatsApp template message.

    Templates must be APPROVED in Meta before they can be sent.
    Use POST /templates/{id}/sync to pull the latest status from Meta.
    """
    redis = await get_redis()
    org_id = current_user.org_id

    content_hash = hashlib.sha256(
        f"{body.template_name}:{body.language_code}:{body.to}".encode()
    ).hexdigest()[:16]
    idem_key = body.idempotency_key or IdempotencyKey.message(str(org_id), body.to, "", content_hash)
    redis_key = f"idem:msg:{idem_key}"

    # 5-second dedup window — prevents accidental double-clicks only
    if await check_and_set(redis, redis_key, ttl=5):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate request — this template was already sent. Please wait a moment before resending.",
        )

    phone, waba = await _get_phone_and_waba(db, body.phone_number_id, org_id)

    # Phase 1 billing: reserve (marketing rate)
    cost = await _get_cost(db, org_id, "marketing")
    txn = None
    if cost > 0:
        txn = await reserve_credits(
            db,
            org_id=org_id,
            amount=cost,
            idempotency_key=IdempotencyKey.wallet_debit(str(org_id), idem_key),
            description=f"Template '{body.template_name}' to {body.to}",
        )
        await db.flush()

    contact = await _upsert_contact(db, org_id, body.to)
    conv = await _get_or_create_conversation(db, org_id, contact.id, phone.id)

    # Send via MetaClient (with rate limiter)
    client = build_client(waba.access_token, redis)
    try:
        result = await client.send_template(
            phone_number_id=phone.phone_number_id,
            to=body.to,
            template_name=body.template_name,
            language_code=body.language_code,
            components=body.components or [],
        )
    except MetaAPIError as exc:
        if txn:
            await rollback_credits(db, txn)
        await db.commit()
        await clear(redis, redis_key)
        raise _meta_error_to_http(exc)

    now = datetime.now(timezone.utc)
    msg = Message(
        org_id=org_id,
        conversation_id=conv.id,
        wa_message_id=result.wa_message_id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        message_type="template",
        content={"template_name": body.template_name, "language": body.language_code, "components": body.components},
        cost_credits=cost,
        idempotency_key=idem_key,
        sent_at=now,
        created_at=now,
    )
    db.add(msg)
    conv.last_message_at = now  # type: ignore[assignment]
    conv.session_expires_at = now + timedelta(hours=SESSION_WINDOW_HOURS)  # type: ignore[assignment]

    await db.flush()
    if txn:
        txn.message_id = msg.id  # type: ignore[assignment]
        await confirm_credits(db, txn)

    await db.commit()
    await db.refresh(msg)
    await _publish(redis, org_id, conv.id, msg)

    logger.info(
        "message.template_sent",
        org_id=str(org_id),
        wa_id=result.wa_message_id,
        template=body.template_name,
        to=body.to,
        cost=cost,
    )

    return {
        "message_id": msg.id,
        "wa_message_id": result.wa_message_id,
        "status": msg.status.value,
        "cost_credits": cost,
    }


# ── Send media ───────────────────────────────────────────────────────────────

_ALLOWED_MEDIA_TYPES = {"image", "document", "audio", "video"}


@router.post("/send/media", response_model=SendMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_media_message(
    current_user: CurrentUser,
    db: DbDep,
    phone_number_id: uuid.UUID = Form(...),
    to: str = Form(...),
    media_type: str = Form(...),
    caption: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> dict:
    """Send an image, document, audio, or video message."""
    if media_type not in _ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"media_type must be one of: {', '.join(sorted(_ALLOWED_MEDIA_TYPES))}",
        )

    redis = await get_redis()
    org_id = current_user.org_id
    phone, waba = await _get_phone_and_waba(db, phone_number_id, org_id)

    content_bytes = await file.read()
    filename = file.filename or f"upload.{media_type}"
    mime_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    contact = await _upsert_contact(db, org_id, to)
    conv = await _get_or_create_conversation(db, org_id, contact.id, phone.id)

    client = build_client(waba.access_token, redis)
    try:
        # Step 1: Upload file to Meta — get back a media_id
        media_id = await client.upload_media(
            phone_number_id=phone.phone_number_id,
            file_bytes=content_bytes,
            mime_type=mime_type,
            filename=filename,
        )

        # Step 2: Send the message referencing the media_id
        if media_type == "image":
            result = await client.send_image(
                phone_number_id=phone.phone_number_id, to=to,
                image_id=media_id, caption=caption or None,
            )
        elif media_type == "document":
            result = await client.send_document(
                phone_number_id=phone.phone_number_id, to=to,
                document_id=media_id, filename=filename, caption=caption or None,
            )
        elif media_type == "audio":
            result = await client.send_audio(
                phone_number_id=phone.phone_number_id, to=to, audio_id=media_id,
            )
        else:  # video
            result = await client.send_video(
                phone_number_id=phone.phone_number_id, to=to,
                video_id=media_id, caption=caption or None,
            )
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    now = datetime.now(timezone.utc)
    idem_key = IdempotencyKey.message(str(org_id), to, result.wa_message_id, media_id[:8])
    msg = Message(
        org_id=org_id,
        conversation_id=conv.id,
        wa_message_id=result.wa_message_id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        message_type=media_type,
        content={"caption": caption or "", "filename": filename, "media_id": media_id},
        cost_credits=0,
        idempotency_key=idem_key,
        sent_at=now,
        created_at=now,
    )
    db.add(msg)
    conv.last_message_at = now  # type: ignore[assignment]
    conv.session_expires_at = now + timedelta(hours=SESSION_WINDOW_HOURS)  # type: ignore[assignment]
    await db.commit()
    await db.refresh(msg)
    await _publish(redis, org_id, conv.id, msg)
    logger.info("message.media_sent", org_id=str(org_id), wa_id=result.wa_message_id, media_type=media_type, to=to, media_id=media_id)
    return {"message_id": msg.id, "wa_message_id": result.wa_message_id, "status": msg.status.value, "cost_credits": 0}


# ── Media proxy ──────────────────────────────────────────────────────────────

@router.get("/media/{media_id}")
async def proxy_media(
    media_id: str,
    db: DbDep,
    token: str = Query(...),
) -> Response:
    """Download Meta media and stream to browser.

    Accepts JWT via ?token= query param so <img src> / <audio src> tags work
    without custom headers. Fetches a fresh temporary URL from Meta each time.
    """
    payload = decode_token(token)
    if not payload or "org_id" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        org_id = uuid.UUID(payload["org_id"])
    except (ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Find any active WABA/phone for this org to get an access token
    phone_result = await db.execute(
        select(PhoneNumber)
        .where(PhoneNumber.org_id == org_id, PhoneNumber.is_active == True)
        .limit(1)
    )
    phone = phone_result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active phone number for this org")

    waba_result = await db.execute(select(WabaAccount).where(WabaAccount.id == phone.waba_id))
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")

    redis = await get_redis()
    client = build_client(waba.access_token, redis)
    try:
        content_bytes, mime_type = await client.download_media(media_id)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    return Response(
        content=content_bytes,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ── Mark as read ──────────────────────────────────────────────────────────────

@router.post("/send/mark-read", status_code=status.HTTP_200_OK)
async def mark_message_read(
    body: MarkReadRequest,
    current_user: CurrentUser,
    db: DbDep,
) -> dict:
    """Mark an inbound message as read (shows blue ticks to the sender).

    Requires the internal message UUID — look it up from GET /conversations/{id}/messages.
    """
    # Resolve message → verify org ownership
    result = await db.execute(
        select(Message).where(
            Message.id == body.message_id,
            Message.org_id == current_user.org_id,
            Message.direction == MessageDirection.inbound,
        )
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inbound message not found",
        )

    if not msg.wa_message_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message has no wa_message_id",
        )

    # Resolve the phone number this conversation is on
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == msg.conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.id == conv.phone_number_id)
    )
    phone = phone_result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")

    waba_result = await db.execute(
        select(WabaAccount).where(WabaAccount.id == phone.waba_id)
    )
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")

    redis = await get_redis()
    client = build_client(waba.access_token, redis)
    try:
        await client.mark_read(
            phone_number_id=phone.phone_number_id,
            wa_message_id=msg.wa_message_id,
        )
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    logger.info(
        "message.marked_read",
        org_id=str(current_user.org_id),
        message_id=str(body.message_id),
        wa_message_id=msg.wa_message_id,
    )
    return {"status": "ok", "wa_message_id": msg.wa_message_id}


# ── Inbox ─────────────────────────────────────────────────────────────────────

@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: CurrentUser,
    db: DbDep,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List conversations for this org, newest first."""
    query = (
        select(Conversation, Contact.phone, Contact.name)
        .join(Contact, Contact.id == Conversation.contact_id)
        .where(Conversation.org_id == current_user.org_id)
        .order_by(Conversation.last_message_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        try:
            s = ConversationStatus(status_filter)
            query = query.where(Conversation.status == s)
        except ValueError:
            pass
    result = await db.execute(query)
    rows = result.all()
    out = []
    for conv, phone, name in rows:
        d = {c.key: getattr(conv, c.key) for c in conv.__table__.columns}
        d["status"] = conv.status.value if hasattr(conv.status, "value") else conv.status
        d["contact_phone"] = phone
        d["contact_name"] = name
        out.append(d)
    return out


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbDep,
) -> None:
    """Delete a conversation and all its messages."""
    from sqlalchemy import delete as sql_delete
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.org_id == current_user.org_id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await db.execute(sql_delete(Message).where(Message.conversation_id == conversation_id))
    await db.delete(conv)
    await db.commit()
    logger.info("conversation.deleted", conversation_id=str(conversation_id), org_id=str(current_user.org_id))


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbDep,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    """List messages in a conversation, oldest first."""
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.org_id == current_user.org_id,
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())

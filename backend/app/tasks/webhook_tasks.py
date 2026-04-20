"""Webhook processing tasks — webhook_queue.

Dispatches saved WebhookEvent rows by event_type:
  inbound_message      → upsert contact, find/create conversation, save message
  status_update        → update message.status + delivered_at/read_at + campaign counts
  template_status_update → update template.status in DB
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from celery import Task
from loguru import logger
from sqlalchemy import select

from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.message import (
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
)
from app.models.webhook import WebhookEvent
from app.models.whatsapp import PhoneNumber

SESSION_WINDOW_HOURS = 24


def _run(coro):
    """Run async code from a sync Celery task (Python 3.10+ safe)."""
    return asyncio.run(coro)


def _make_session():
    """Create a fresh engine + session for each task to avoid event loop conflicts."""
    # Import all models so SQLAlchemy metadata is fully populated (FK resolution)
    import app.models.org  # noqa: F401
    import app.models.user  # noqa: F401
    import app.models.contact  # noqa: F401
    import app.models.message  # noqa: F401
    import app.models.whatsapp  # noqa: F401
    import app.models.webhook  # noqa: F401
    import app.models.campaign  # noqa: F401
    import app.models.wallet  # noqa: F401
    import app.models.media  # noqa: F401
    import app.models.analytics  # noqa: F401
    import app.models.automation  # noqa: F401
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    from app.core.config import settings
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


# ── Main dispatcher ───────────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.webhook_tasks.process_webhook_event",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    acks_late=True,
    queue="webhook_queue",
)
def process_webhook_event(self: Task, event_id: str) -> None:
    _run(_process_event(self, event_id))


async def _process_event(task: Task, event_id: str) -> None:
    AsyncSessionLocal = _make_session()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WebhookEvent).where(WebhookEvent.id == uuid.UUID(event_id))
        )
        event = result.scalar_one_or_none()
        if not event:
            logger.warning("webhook.event_not_found", event_id=event_id)
            return

        if event.processed:
            logger.info("webhook.already_processed", event_id=event_id)
            return

        try:
            event_type = event.event_type
            payload = event.payload or {}

            if event_type == "inbound_message":
                await _handle_inbound_message(db, payload)
            elif event_type == "status_update":
                await _handle_status_update(db, payload)
            elif event_type == "template_status_update":
                await _handle_template_status(db, payload)
            else:
                logger.debug("webhook.unhandled_type", event_type=event_type)

            event.processed = True  # type: ignore[assignment]
            await db.commit()
            logger.info("webhook.processed", event_id=event_id, event_type=event_type)

        except Exception as exc:
            event.retry_count = (event.retry_count or 0) + 1  # type: ignore[assignment]
            event.last_error = str(exc)[:500]  # type: ignore[assignment]
            await db.commit()
            logger.error("webhook.processing_failed", event_id=event_id, error=str(exc))
            raise task.retry(exc=exc)


# ── Inbound message ───────────────────────────────────────────────────────────

async def _handle_inbound_message(db, payload: dict) -> None:
    """Upsert contact + conversation, save inbound message, publish to Redis."""
    phone_number_id_meta = payload.get("phone_number_id", "")
    msg_data = payload.get("message", {})

    wa_message_id = msg_data.get("id", "")
    from_phone = msg_data.get("from", "")
    msg_type = msg_data.get("type", "text")

    # Normalize to E.164 — Meta sends numbers without leading +
    if from_phone and not from_phone.startswith("+"):
        from_phone = "+" + from_phone

    if not wa_message_id or not from_phone:
        return

    # Idempotency — skip if already saved
    existing = await db.execute(
        select(Message).where(Message.wa_message_id == wa_message_id)
    )
    if existing.scalar_one_or_none():
        logger.debug("webhook.inbound_duplicate", wa_message_id=wa_message_id)
        return

    # Resolve org from Meta's phone_number_id
    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.phone_number_id == phone_number_id_meta)
    )
    phone_row = phone_result.scalar_one_or_none()
    if not phone_row:
        logger.warning("webhook.phone_not_found", phone_number_id=phone_number_id_meta)
        return

    org_id = phone_row.org_id

    # Upsert contact
    contact = await _upsert_contact(db, org_id, from_phone, msg_data)

    # Find or create conversation
    conv = await _get_or_create_conversation(db, org_id, contact.id, phone_row.id)

    # Extract content per message type
    content = _extract_content(msg_type, msg_data)
    now = datetime.now(timezone.utc)

    msg = Message(
        org_id=org_id,
        conversation_id=conv.id,
        wa_message_id=wa_message_id,
        direction=MessageDirection.inbound,
        status=MessageStatus.delivered,
        message_type=msg_type,
        content=content,
        idempotency_key=f"inbound:{wa_message_id}",
        created_at=now,
    )
    db.add(msg)
    conv.last_message_at = now  # type: ignore[assignment]
    conv.session_expires_at = now + timedelta(hours=SESSION_WINDOW_HOURS)  # type: ignore[assignment]
    await db.flush()

    # Publish to Redis for live inbox WebSocket
    await _publish_event(org_id, conv.id, msg, "new_message")

    logger.info(
        "webhook.inbound_saved",
        org_id=str(org_id),
        wa_message_id=wa_message_id,
        from_phone=from_phone,
        msg_type=msg_type,
    )


# ── Status update ─────────────────────────────────────────────────────────────

async def _handle_status_update(db, payload: dict) -> None:
    """Update message delivery status + campaign counters."""
    status_data = payload.get("status", {})
    wa_message_id = status_data.get("id", "")
    new_status = status_data.get("status", "")
    recipient_phone = "+" + status_data.get("recipient_id", "").lstrip("+") if status_data.get("recipient_id") else None

    if not wa_message_id or not new_status:
        return

    result = await db.execute(
        select(Message).where(Message.wa_message_id == wa_message_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        logger.debug("webhook.status_msg_not_found", wa_message_id=wa_message_id)
        return

    now = datetime.now(timezone.utc)
    status_map = {
        "delivered": (MessageStatus.delivered, "delivered_at"),
        "read":      (MessageStatus.read, "read_at"),
        "failed":    (MessageStatus.failed, None),
    }

    if new_status in status_map:
        status_enum, timestamp_field = status_map[new_status]
        msg.status = status_enum  # type: ignore[assignment]
        if timestamp_field:
            setattr(msg, timestamp_field, now)
        if new_status == "failed":
            errors = status_data.get("errors", [])
            msg.failed_reason = errors[0].get("message", "unknown") if errors else "unknown"  # type: ignore[assignment]

    # Update campaign counters if applicable
    if msg.campaign_id and new_status in ("delivered", "read", "failed"):
        await _update_campaign_counts(db, msg.campaign_id, new_status, recipient_phone)

    await db.flush()

    # Publish status change to inbox WebSocket
    if msg.org_id:
        await _publish_status_event(msg.org_id, msg, new_status)

    logger.debug("webhook.status_updated", wa_message_id=wa_message_id, status=new_status)


# ── Template status update ────────────────────────────────────────────────────

async def _handle_template_status(db, payload: dict) -> None:
    """Update template status in DB when Meta approves/rejects."""
    from app.models.whatsapp import MessageTemplate, TemplateStatus

    template_name = payload.get("message_template_name", "")
    template_language = payload.get("message_template_language", "")
    event = payload.get("event", "")
    reason = payload.get("reason")

    if not template_name or not event:
        return

    # Map Meta event → our TemplateStatus enum
    event_to_status = {
        "APPROVED": TemplateStatus.APPROVED,
        "REJECTED": TemplateStatus.REJECTED,
        "DISABLED": TemplateStatus.REJECTED,
        "FLAGGED": TemplateStatus.PAUSED,
        "REINSTATED": TemplateStatus.APPROVED,
        "PAUSED": TemplateStatus.PAUSED,
    }
    new_status = event_to_status.get(event)
    if not new_status:
        return

    result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.name == template_name,
            MessageTemplate.language == template_language,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        logger.warning(
            "webhook.template_not_found",
            name=template_name,
            language=template_language,
        )
        return

    template.status = new_status  # type: ignore[assignment]
    if reason:
        template.rejection_reason = reason  # type: ignore[assignment]
    await db.flush()

    logger.info(
        "webhook.template_status_updated",
        name=template_name,
        language=template_language,
        status=new_status.value,
    )


# ── Campaign counter update ───────────────────────────────────────────────────

async def _update_campaign_counts(db, campaign_id: uuid.UUID, new_status: str, recipient_phone: str | None = None) -> None:
    from app.models.campaign import Campaign, CampaignRecipient, RecipientStatus
    from sqlalchemy import update

    status_map = {
        "delivered": RecipientStatus.delivered,
        "read": RecipientStatus.read,
        "failed": RecipientStatus.failed,
    }
    recipient_status = status_map.get(new_status)
    if not recipient_status:
        return

    # Update only the specific recipient, not all recipients in the campaign
    if recipient_phone:
        await db.execute(
            update(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.phone == recipient_phone,
            )
            .values(status=recipient_status)
        )

    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if campaign:
        current = getattr(campaign, f"{new_status}_count", 0) or 0
        setattr(campaign, f"{new_status}_count", current + 1)

    await db.flush()


# ── Beat retry scanner ────────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.webhook_tasks.retry_failed_webhooks",
    acks_late=True,
    queue="webhook_queue",
)
def retry_failed_webhooks() -> None:
    _run(_retry_scan())


async def _retry_scan() -> None:
    AsyncSessionLocal = _make_session()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WebhookEvent).where(
                WebhookEvent.processed == False,
                WebhookEvent.retry_count < 5,
            ).limit(100)
        )
        events = result.scalars().all()
        for event in events:
            process_webhook_event.delay(str(event.id))
        if events:
            logger.info("webhook.retry_scan", count=len(events))


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _upsert_contact(db, org_id: uuid.UUID, phone: str, msg_data: dict) -> Contact:
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    result = await db.execute(
        select(Contact).where(Contact.org_id == org_id, Contact.phone == phone)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        contact = Contact(org_id=org_id, phone=phone)
        db.add(contact)
        await db.flush()
    return contact


async def _get_or_create_conversation(
    db,
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


def _extract_content(msg_type: str, msg_data: dict) -> dict:
    if msg_type == "text":
        return {"body": msg_data.get("text", {}).get("body", "")}
    if msg_type in ("image", "audio", "video", "document", "sticker"):
        media = msg_data.get(msg_type, {})
        return {
            "id": media.get("id"),
            "mime_type": media.get("mime_type"),
            "sha256": media.get("sha256"),
            "caption": media.get("caption"),
            "filename": media.get("filename"),
        }
    if msg_type == "button":
        btn = msg_data.get("button", {})
        return {"text": btn.get("text"), "payload": btn.get("payload")}
    if msg_type == "interactive":
        return msg_data.get("interactive", {})
    if msg_type == "location":
        loc = msg_data.get("location", {})
        return {
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "name": loc.get("name"),
            "address": loc.get("address"),
        }
    if msg_type == "reaction":
        react = msg_data.get("reaction", {})
        return {"emoji": react.get("emoji"), "message_id": react.get("message_id")}
    return {"raw": msg_data.get(msg_type, {})}


async def _publish_event(org_id, conv_id, msg: Message, event_name: str) -> None:
    try:
        from app.core.redis_client import get_redis
        redis = await get_redis()
        payload = {
            "event": event_name,
            "conversation_id": str(conv_id),
            "message_id": str(msg.id),
            "direction": msg.direction.value,
            "status": msg.status.value,
            "message_type": msg.message_type,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
        await redis.publish(f"inbox:{org_id}", json.dumps(payload))
    except Exception as exc:
        logger.warning("webhook.redis_publish_failed", error=str(exc))


async def _publish_status_event(org_id, msg: Message, new_status: str) -> None:
    try:
        from app.core.redis_client import get_redis
        redis = await get_redis()
        payload = {
            "event": "message_status_update",
            "message_id": str(msg.id),
            "wa_message_id": msg.wa_message_id,
            "status": new_status,
        }
        await redis.publish(f"inbox:{org_id}", json.dumps(payload))
    except Exception as exc:
        logger.warning("webhook.redis_status_publish_failed", error=str(exc))

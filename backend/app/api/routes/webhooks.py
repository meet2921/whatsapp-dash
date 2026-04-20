"""Meta webhook receiver — save-first, process-async.

GET  /webhooks/meta  — verification challenge (Meta sends this once on setup)
POST /webhooks/meta  — inbound events (messages, statuses, template status)

Flow:
  1. Verify X-Hub-Signature-256 via MetaWebhook.verify_signature()
  2. Parse payload via MetaWebhook.parse() → typed objects
  3. Redis idempotency fast-path per change
  4. INSERT into webhook_events (processed=FALSE)
  5. Enqueue Celery task (webhook_queue)
  6. Return HTTP 200 immediately (< 200ms target)
"""
import json
from datetime import datetime, timezone
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.idempotency import IdempotencyKey, check_and_set
from app.core.redis_client import get_redis
from app.integration.meta.exceptions import MetaWebhookSignatureError
from app.integration.meta.webhook import MetaWebhook
from app.models.webhook import WebhookEvent

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


# ── Verification challenge ─────────────────────────────────────────────────────

@router.get("/meta")
async def meta_webhook_verify(request: Request):
    """
    Meta webhook verification endpoint
    MUST return plain text challenge
    """

    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    logger.info(
        "webhook.meta.verify_request",
        mode=mode,
        token=token,
        challenge=challenge,
    )

    # Validate inputs
    if not mode or not token or not challenge:
        logger.error("webhook.meta.missing_params")
        return Response(content="Missing params", status_code=400)

    if mode == "subscribe" and token == settings.META_VERIFY_TOKEN:
        logger.info("webhook.meta.verified_success")
        return Response(content=challenge, media_type="text/plain", status_code=200)

    logger.warning("webhook.meta.verify_failed")
    return Response(content="Verification failed", status_code=403)

# ── Inbound events ─────────────────────────────────────────────────────────────

@router.post("/meta", status_code=status.HTTP_200_OK)
async def meta_webhook_receive(
    request: Request,
    db: DbDep,
) -> dict:
    """Receive Meta webhook events. Returns HTTP 200 as fast as possible."""
    raw_body = await request.body()

    # ── 1. Verify HMAC-SHA256 signature ──────────────────────────────────────
    try:
        MetaWebhook.verify_signature(
            app_secret=settings.META_APP_SECRET,
            raw_body=raw_body,
            signature_header=request.headers.get("X-Hub-Signature-256", ""),
        )
    except MetaWebhookSignatureError as exc:
        logger.warning("webhook.meta.signature_failed", error=str(exc), ip=request.client.host if request.client else "unknown")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # ── 2. Parse payload ──────────────────────────────────────────────────────
    try:
        raw_payload: dict = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    parsed = MetaWebhook.parse(raw_payload)

    if parsed.is_empty:
        return {"status": "ok", "queued": 0}

    redis = await get_redis()
    queued = 0

    # ── 3-5. Idempotency → persist → enqueue ─────────────────────────────────
    for change in parsed.changes:
        # Process inbound messages
        for msg in change.messages:
            idem_key = IdempotencyKey.webhook("meta", msg.wa_message_id, "inbound_message")
            if await check_and_set(redis, idem_key):
                logger.info("webhook.meta.duplicate_message", wa_id=msg.wa_message_id)
                continue

            event = WebhookEvent(
                source="meta",
                event_type="inbound_message",
                payload={
                    "phone_number_id": change.phone_number_id,
                    "waba_id": change.waba_id,
                    "message": msg.raw,
                },
                idempotency_key=idem_key,
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            await db.flush()

            from app.tasks.webhook_tasks import process_webhook_event
            process_webhook_event.delay(str(event.id))
            queued += 1
            logger.info(
                "webhook.meta.message_queued",
                event_id=str(event.id),
                from_phone=msg.from_phone,
                msg_type=msg.message_type,
                phone_number_id=change.phone_number_id,
            )

        # Process status updates
        for status_update in change.statuses:
            idem_key = IdempotencyKey.webhook(
                "meta", status_update.wa_message_id, f"status_{status_update.status}"
            )
            if await check_and_set(redis, idem_key):
                continue

            event = WebhookEvent(
                source="meta",
                event_type="status_update",
                payload={
                    "phone_number_id": change.phone_number_id,
                    "status": {
                        "id": status_update.wa_message_id,
                        "recipient_id": status_update.recipient_phone,
                        "status": status_update.status,
                        "timestamp": str(status_update.timestamp),
                        "conversation": {
                            "id": status_update.conversation_id,
                            "origin": {"type": status_update.conversation_origin},
                        } if status_update.conversation_id else {},
                        "errors": status_update.errors,
                    },
                },
                idempotency_key=idem_key,
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            await db.flush()

            from app.tasks.webhook_tasks import process_webhook_event
            process_webhook_event.delay(str(event.id))
            queued += 1
            logger.info(
                "webhook.meta.status_queued",
                event_id=str(event.id),
                wa_message_id=status_update.wa_message_id,
                status=status_update.status,
            )

        # Process template status updates
        for tsu in change.template_updates:
            idem_key = IdempotencyKey.webhook(
                "meta", tsu.message_template_id, f"template_{tsu.event}"
            )
            if await check_and_set(redis, idem_key):
                continue

            event = WebhookEvent(
                source="meta",
                event_type="template_status_update",
                payload={
                    "waba_id": change.waba_id,
                    "message_template_id": tsu.message_template_id,
                    "message_template_name": tsu.message_template_name,
                    "message_template_language": tsu.message_template_language,
                    "event": tsu.event,
                    "reason": tsu.reason,
                },
                idempotency_key=idem_key,
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            await db.flush()

            from app.tasks.webhook_tasks import process_webhook_event
            process_webhook_event.delay(str(event.id))
            queued += 1
            logger.info(
                "webhook.meta.template_status_queued",
                event_id=str(event.id),
                template=tsu.message_template_name,
                event_type=tsu.event,
            )

    await db.commit()
    return {"status": "ok", "queued": queued}

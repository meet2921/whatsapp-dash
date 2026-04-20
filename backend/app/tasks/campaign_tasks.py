"""Campaign dispatch task — campaign_queue.

run_campaign(campaign_id, org_id):
  - Loads all QUEUED recipients in batches of 50
  - Sends each via MetaClient (respects Meta rate limit)
  - Updates recipient status + campaign counters atomically
  - Respects PAUSED status — stops mid-run if paused
  - Marks campaign COMPLETED when all recipients processed
  - Marks campaign FAILED on any unrecoverable error
"""
import asyncio
import uuid
from datetime import datetime, timezone

from loguru import logger

from app.celery_app import celery_app

BATCH_SIZE = 50
RATE_LIMIT_DELAY = 0.05  # 50ms between sends → ~20/s (well under Meta's 80/s limit)


def _run(coro):
    return asyncio.run(coro)


def _make_session():
    import app.models.org        # noqa: F401
    import app.models.user       # noqa: F401
    import app.models.contact    # noqa: F401
    import app.models.message    # noqa: F401
    import app.models.whatsapp   # noqa: F401
    import app.models.webhook    # noqa: F401
    import app.models.campaign   # noqa: F401
    import app.models.wallet     # noqa: F401
    import app.models.media      # noqa: F401
    import app.models.analytics  # noqa: F401
    import app.models.automation # noqa: F401
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    from app.core.config import settings
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@celery_app.task(
    name="app.tasks.campaign_tasks.run_campaign",
    bind=True,
    max_retries=0,  # campaign task manages its own retries per-recipient
    queue="campaign_queue",
)
def run_campaign(self, campaign_id: str, org_id: str) -> dict:
    """Dispatch all QUEUED recipients for a campaign."""
    logger.info("campaign.task_started", campaign_id=campaign_id)
    return _run(_run_campaign_async(campaign_id, org_id))


async def _run_campaign_async(campaign_id_str: str, org_id_str: str) -> dict:
    from sqlalchemy import select
    from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
    from app.models.whatsapp import MessageTemplate, PhoneNumber, WabaAccount
    from app.integration.meta.client import MetaClient

    SessionLocal = _make_session()
    campaign_id = uuid.UUID(campaign_id_str)
    org_id = uuid.UUID(org_id_str)

    sent = delivered_err = 0

    async with SessionLocal() as db:
        # Load campaign
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            logger.error("campaign.not_found", campaign_id=campaign_id_str)
            return {"error": "not found"}

        if campaign.status not in (CampaignStatus.running,):
            logger.info("campaign.not_running", campaign_id=campaign_id_str, status=campaign.status.value)
            return {"skipped": True}

        try:
            # Load template + phone + waba
            t_result = await db.execute(select(MessageTemplate).where(MessageTemplate.id == campaign.template_id))
            template = t_result.scalar_one_or_none()
            if not template:
                campaign.status = CampaignStatus.failed  # type: ignore[assignment]
                await db.commit()
                return {"error": "template not found"}

            p_result = await db.execute(select(PhoneNumber).where(PhoneNumber.id == campaign.phone_number_id))
            phone = p_result.scalar_one_or_none()
            if not phone:
                campaign.status = CampaignStatus.failed  # type: ignore[assignment]
                await db.commit()
                return {"error": "phone not found"}

            w_result = await db.execute(select(WabaAccount).where(WabaAccount.id == phone.waba_id))
            waba = w_result.scalar_one_or_none()
            if not waba:
                campaign.status = CampaignStatus.failed  # type: ignore[assignment]
                await db.commit()
                return {"error": "waba not found"}

            logger.info(
                "campaign.dispatch_starting",
                campaign_id=campaign_id_str,
                template=template.name,
                phone_number_id=phone.phone_number_id,
                total_recipients=campaign.total_recipients,
            )

            client = MetaClient(waba.access_token)

            # Process in batches
            while True:
                # Re-check campaign status (may have been paused)
                await db.refresh(campaign)
                if campaign.status != CampaignStatus.running:
                    logger.info("campaign.halted", campaign_id=campaign_id_str, status=campaign.status.value)
                    break

                # Fetch next batch of queued recipients
                batch_result = await db.execute(
                    select(CampaignRecipient)
                    .where(
                        CampaignRecipient.campaign_id == campaign_id,
                        CampaignRecipient.status == RecipientStatus.queued,
                    )
                    .order_by(CampaignRecipient.id)
                    .limit(BATCH_SIZE)
                )
                recipients = list(batch_result.scalars().all())

                if not recipients:
                    # All done
                    campaign.status = CampaignStatus.completed  # type: ignore[assignment]
                    campaign.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
                    await db.commit()
                    logger.info("campaign.completed", campaign_id=campaign_id_str, sent=sent)
                    break

                for recipient in recipients:
                    # Re-check pause between each send
                    if campaign.status != CampaignStatus.running:
                        break
                    try:
                        # Meta API expects E.164 without '+'
                        to_number = recipient.phone.lstrip("+")
                        result = await client.send_template(
                            phone_number_id=phone.phone_number_id,
                            to=to_number,
                            template_name=template.name,
                            language_code=template.language,
                            components=[],
                        )
                        recipient.status = RecipientStatus.sent  # type: ignore[assignment]
                        campaign.sent_count = campaign.sent_count + 1  # type: ignore[assignment]
                        sent += 1
                        logger.debug("campaign.sent", campaign_id=campaign_id_str, to=to_number, wa_id=result.wa_message_id)
                    except Exception as exc:
                        recipient.status = RecipientStatus.failed  # type: ignore[assignment]
                        recipient.error_message = str(exc)[:500]  # type: ignore[assignment]
                        campaign.failed_count = campaign.failed_count + 1  # type: ignore[assignment]
                        delivered_err += 1
                        logger.warning("campaign.send_failed", campaign_id=campaign_id_str, to=recipient.phone, error=str(exc))

                    await asyncio.sleep(RATE_LIMIT_DELAY)

                await db.commit()

        except Exception as exc:
            # Unrecoverable error — mark campaign as failed
            logger.error("campaign.task_error", campaign_id=campaign_id_str, error=str(exc), exc_info=True)
            try:
                await db.refresh(campaign)
                campaign.status = CampaignStatus.failed  # type: ignore[assignment]
                await db.commit()
            except Exception:
                pass
            return {"error": str(exc)}

    return {"sent": sent, "failed": delivered_err}

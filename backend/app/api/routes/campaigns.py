"""Campaigns — bulk broadcast of approved templates to contact lists.

POST   /campaigns                    — create campaign (draft)
GET    /campaigns                    — list campaigns
GET    /campaigns/{id}               — get campaign + stats
PATCH  /campaigns/{id}               — update draft campaign
DELETE /campaigns/{id}               — delete draft campaign
POST   /campaigns/{id}/launch        — launch (schedule or immediate)
POST   /campaigns/{id}/pause         — pause running campaign
POST   /campaigns/{id}/resume        — resume paused campaign
GET    /campaigns/{id}/recipients    — list recipients + per-row status
POST   /campaigns/{id}/recipients    — add recipients (phone list or tag)
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, OrgAdmin
from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
from app.models.contact import Contact, ContactTag
from app.models.whatsapp import MessageTemplate, PhoneNumber

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str
    template_id: uuid.UUID
    phone_number_id: uuid.UUID
    scheduled_at: datetime | None = None
    template_variables: dict | None = None  # {"HEADER-1": "val", "BODY-1": "val", ...}


class CampaignUpdate(BaseModel):
    name: str | None = None
    template_id: uuid.UUID | None = None
    phone_number_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    template_variables: dict | None = None


class AddRecipientsBody(BaseModel):
    phones: list[str] | None = None           # explicit phone list
    tag_id: uuid.UUID | None = None           # add all contacts with this tag
    all_opted_in: bool = False                # add all opted-in contacts


class LaunchBody(BaseModel):
    scheduled_at: datetime | None = None     # None = immediate


def _campaign_to_dict(c: Campaign) -> dict:
    return {
        "id": str(c.id),
        "org_id": str(c.org_id),
        "name": c.name,
        "template_id": str(c.template_id) if c.template_id else None,
        "phone_number_id": str(c.phone_number_id) if c.phone_number_id else None,
        "status": c.status.value,
        "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "total_recipients": c.total_recipients,
        "sent_count": c.sent_count,
        "delivered_count": c.delivered_count,
        "read_count": c.read_count,
        "failed_count": c.failed_count,
        "estimated_cost": float(c.estimated_cost) if c.estimated_cost else None,
        "actual_cost": float(c.actual_cost) if c.actual_cost else None,
        "template_variables": c.template_variables or {},
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


async def _assert_draft(campaign: Campaign) -> None:
    if campaign.status not in (CampaignStatus.draft, CampaignStatus.scheduled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot modify a campaign in '{campaign.status.value}' state",
        )


async def _get_campaign(campaign_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> Campaign:
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_campaigns(
    current_user: CurrentUser,
    db: DbDep,
    status_filter: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
) -> dict:
    q = (
        select(Campaign)
        .where(Campaign.org_id == current_user.org_id)
        .order_by(Campaign.created_at.desc())
    )
    if status_filter:
        try:
            q = q.where(Campaign.status == CampaignStatus(status_filter))
        except ValueError:
            pass

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    result = await db.execute(q.offset(offset).limit(limit))
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_campaign_to_dict(c) for c in result.scalars().all()],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, current_user: OrgAdmin, db: DbDep) -> dict:
    # Validate template belongs to org
    t_result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.id == body.template_id,
            MessageTemplate.org_id == current_user.org_id,
        )
    )
    if not t_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Template not found")

    # Validate phone number belongs to org
    p_result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == body.phone_number_id,
            PhoneNumber.org_id == current_user.org_id,
            PhoneNumber.is_active == True,
        )
    )
    if not p_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Phone number not found or inactive")

    campaign = Campaign(
        org_id=current_user.org_id,
        name=body.name,
        template_id=body.template_id,
        phone_number_id=body.phone_number_id,
        status=CampaignStatus.draft,
        scheduled_at=body.scheduled_at,
        created_by=current_user.id,
        template_variables=body.template_variables or {},
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    logger.info("campaign.created", org_id=str(current_user.org_id), campaign_id=str(campaign.id))
    return _campaign_to_dict(campaign)


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: uuid.UUID, current_user: CurrentUser, db: DbDep) -> dict:
    c = await _get_campaign(campaign_id, current_user.org_id, db)
    return _campaign_to_dict(c)


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: uuid.UUID, body: CampaignUpdate, current_user: OrgAdmin, db: DbDep) -> dict:
    c = await _get_campaign(campaign_id, current_user.org_id, db)
    await _assert_draft(c)

    if body.name is not None:
        c.name = body.name  # type: ignore[assignment]
    if body.template_id is not None:
        c.template_id = body.template_id  # type: ignore[assignment]
    if body.phone_number_id is not None:
        c.phone_number_id = body.phone_number_id  # type: ignore[assignment]
    if body.scheduled_at is not None:
        c.scheduled_at = body.scheduled_at  # type: ignore[assignment]
    if body.template_variables is not None:
        c.template_variables = body.template_variables  # type: ignore[assignment]

    await db.commit()
    await db.refresh(c)
    return _campaign_to_dict(c)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> None:
    c = await _get_campaign(campaign_id, current_user.org_id, db)
    if c.status in (CampaignStatus.running,):
        raise HTTPException(status_code=409, detail="Pause the campaign before deleting")
    await db.delete(c)
    await db.commit()


# ── Recipients ────────────────────────────────────────────────────────────────

@router.get("/{campaign_id}/recipients")
async def list_recipients(
    campaign_id: uuid.UUID, current_user: CurrentUser, db: DbDep,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    status_filter: str | None = Query(default=None),
) -> dict:
    await _get_campaign(campaign_id, current_user.org_id, db)  # auth check

    q = select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
    if status_filter:
        try:
            q = q.where(CampaignRecipient.status == RecipientStatus(status_filter))
        except ValueError:
            pass

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    result = await db.execute(q.offset(offset).limit(limit))

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": str(r.id),
                "phone": r.phone,
                "status": r.status.value,
                "template_variables": r.template_variables,
                "error_message": r.error_message,
            }
            for r in result.scalars().all()
        ],
    }


@router.post("/{campaign_id}/recipients", status_code=status.HTTP_200_OK)
async def add_recipients(
    campaign_id: uuid.UUID, body: AddRecipientsBody, current_user: OrgAdmin, db: DbDep
) -> dict:
    """Add recipients to a draft campaign.

    Three modes:
    - phones: explicit list of E.164 phone numbers
    - tag_id: all opted-in contacts with this tag
    - all_opted_in: all opted-in contacts in the org
    """
    c = await _get_campaign(campaign_id, current_user.org_id, db)
    await _assert_draft(c)

    phones: list[str] = []

    if body.phones:
        phones = [p if p.startswith("+") else "+" + p for p in body.phones]
    elif body.tag_id:
        result = await db.execute(
            select(Contact.phone)
            .join(ContactTag, ContactTag.contact_id == Contact.id)
            .where(
                Contact.org_id == current_user.org_id,
                Contact.is_opted_in == True,
                ContactTag.tag_id == body.tag_id,
            )
        )
        phones = [r[0] for r in result.all()]
    elif body.all_opted_in:
        result = await db.execute(
            select(Contact.phone).where(
                Contact.org_id == current_user.org_id,
                Contact.is_opted_in == True,
            )
        )
        phones = [r[0] for r in result.all()]

    if not phones:
        return {"added": 0, "total_recipients": c.total_recipients}

    # Get existing phones to avoid duplicates
    existing_result = await db.execute(
        select(CampaignRecipient.phone).where(CampaignRecipient.campaign_id == campaign_id)
    )
    existing_phones = {r[0] for r in existing_result.all()}

    added = 0
    for phone in phones:
        if phone in existing_phones:
            continue
        db.add(CampaignRecipient(
            campaign_id=campaign_id,
            phone=phone,
            status=RecipientStatus.queued,
        ))
        existing_phones.add(phone)
        added += 1

    c.total_recipients = c.total_recipients + added  # type: ignore[assignment]
    await db.commit()
    await db.refresh(c)
    logger.info("campaign.recipients_added", campaign_id=str(campaign_id), added=added)
    return {"added": added, "total_recipients": c.total_recipients}


# ── Launch / Pause / Resume ───────────────────────────────────────────────────

@router.post("/{campaign_id}/launch", status_code=status.HTTP_200_OK)
async def launch_campaign(
    campaign_id: uuid.UUID, body: LaunchBody, current_user: OrgAdmin, db: DbDep
) -> dict:
    """Launch a campaign — immediate or scheduled."""
    c = await _get_campaign(campaign_id, current_user.org_id, db)
    if c.status not in (CampaignStatus.draft, CampaignStatus.scheduled):
        raise HTTPException(status_code=409, detail=f"Cannot launch a campaign in '{c.status.value}' state")
    if c.total_recipients == 0:
        raise HTTPException(status_code=400, detail="Add recipients before launching")

    now = datetime.now(timezone.utc)
    scheduled_at = body.scheduled_at or now

    if scheduled_at <= now:
        # Immediate — dispatch to Celery
        c.status = CampaignStatus.running  # type: ignore[assignment]
        c.started_at = now  # type: ignore[assignment]
        await db.commit()
        await db.refresh(c)

        # Import here to avoid circular at module load
        from app.tasks.campaign_tasks import run_campaign
        run_campaign.delay(str(campaign_id), str(current_user.org_id))
        logger.info("campaign.launched", campaign_id=str(campaign_id))
    else:
        # Scheduled
        c.status = CampaignStatus.scheduled  # type: ignore[assignment]
        c.scheduled_at = scheduled_at  # type: ignore[assignment]
        await db.commit()
        await db.refresh(c)
        logger.info("campaign.scheduled", campaign_id=str(campaign_id), at=scheduled_at.isoformat())

    return _campaign_to_dict(c)


@router.post("/{campaign_id}/pause", status_code=status.HTTP_200_OK)
async def pause_campaign(campaign_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> dict:
    c = await _get_campaign(campaign_id, current_user.org_id, db)
    if c.status != CampaignStatus.running:
        raise HTTPException(status_code=409, detail="Only running campaigns can be paused")
    c.status = CampaignStatus.paused  # type: ignore[assignment]
    await db.commit()
    await db.refresh(c)
    logger.info("campaign.paused", campaign_id=str(campaign_id))
    return _campaign_to_dict(c)


@router.post("/{campaign_id}/resume", status_code=status.HTTP_200_OK)
async def resume_campaign(campaign_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> dict:
    c = await _get_campaign(campaign_id, current_user.org_id, db)
    if c.status != CampaignStatus.paused:
        raise HTTPException(status_code=409, detail="Only paused campaigns can be resumed")
    c.status = CampaignStatus.running  # type: ignore[assignment]
    await db.commit()
    await db.refresh(c)

    from app.tasks.campaign_tasks import run_campaign
    run_campaign.delay(str(campaign_id), str(current_user.org_id))
    logger.info("campaign.resumed", campaign_id=str(campaign_id))
    return _campaign_to_dict(c)

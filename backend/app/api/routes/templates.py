"""Message templates — fully wired to Meta API.

Every mutating action (create, update, delete) is mirrored to Meta in real time.
The local DB is the cache; Meta is the source of truth for status.

POST   /templates             — submit to Meta + save to DB
GET    /templates             — list from DB
GET    /templates/{id}        — get from DB
PATCH  /templates/{id}        — update components on Meta + DB
DELETE /templates/{id}        — delete from Meta + DB
POST   /templates/{id}/sync   — pull latest status from Meta → update DB
POST   /templates/sync-all    — pull all templates for a WABA from Meta → upsert DB
"""
import uuid
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import OrgAdmin
from app.integration.meta.deps import build_client
from app.integration.meta.exceptions import MetaAPIError, MetaAuthError
from app.models.whatsapp import MessageTemplate, TemplateCategory, TemplateStatus, WabaAccount
from app.schemas.whatsapp import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["Templates"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_template_and_waba(
    template_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[MessageTemplate, WabaAccount]:
    result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.id == template_id,
            MessageTemplate.org_id == org_id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    waba_result = await db.execute(
        select(WabaAccount).where(WabaAccount.id == t.waba_id)
    )
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")
    return t, waba


def _meta_error_to_http(exc: MetaAPIError) -> HTTPException:
    if isinstance(exc, MetaAuthError):
        if exc.error_type == "OAuthException":
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "PERMISSION_ERROR: The access token for this WABA does not have the "
                    "'whatsapp_business_management' permission required to create templates. "
                    "Go to Meta Business Manager → System Users, generate a new token with "
                    "both 'whatsapp_business_messaging' AND 'whatsapp_business_management' scopes, "
                    "then update it in WABA Accounts."
                ),
            )
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Meta access token is invalid or expired. "
                "Go to WABA Accounts and reconnect with a valid System User Token."
            ),
        )
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Meta API error: {exc}")


def _apply_meta_status(t: MessageTemplate, meta_t: dict) -> None:
    """Update a template record from a Meta template dict (in-place)."""
    t.meta_template_id = meta_t.get("id")  # type: ignore[assignment]
    raw_status = meta_t.get("status", "PENDING").upper()
    try:
        t.status = TemplateStatus(raw_status)  # type: ignore[assignment]
    except ValueError:
        pass
    t.rejection_reason = meta_t.get("rejected_reason") or meta_t.get("rejection_reason")  # type: ignore[assignment]


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    current_user: OrgAdmin,
    db: DbDep,
) -> MessageTemplate:
    """Submit a new template to Meta for approval and save it locally.

    Meta will review the template asynchronously. Use GET /templates/{id}/sync
    to check the approval status, or wait for the webhook to update it automatically.

    Template name rules: lowercase letters, numbers, underscores only. No spaces.
    """
    waba_result = await db.execute(
        select(WabaAccount).where(
            WabaAccount.id == body.waba_id,
            WabaAccount.org_id == current_user.org_id,
        )
    )
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")

    try:
        category = TemplateCategory(body.category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category '{body.category}'. Must be: MARKETING, UTILITY, or AUTHENTICATION",
        )

    # Submit to Meta first
    client = build_client(waba.access_token)
    try:
        meta_resp = await client.submit_template(
            waba_id=waba.waba_id,
            name=body.name,
            category=body.category,
            language=body.language,
            components=body.components,
        )
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    template = MessageTemplate(
        org_id=current_user.org_id,
        waba_id=body.waba_id,
        name=body.name,
        category=category,
        language=body.language,
        components=body.components,
        meta_template_id=meta_resp.get("id"),
        status=TemplateStatus(meta_resp.get("status", "PENDING").upper())
        if meta_resp.get("status", "PENDING").upper() in TemplateStatus._value2member_map_
        else TemplateStatus.PENDING,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info(
        "template.created",
        org_id=str(current_user.org_id),
        name=body.name,
        meta_id=template.meta_template_id,
        meta_status=meta_resp.get("status"),
    )
    return template


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    current_user: OrgAdmin,
    db: DbDep,
    status_filter: str | None = None,
) -> list[MessageTemplate]:
    """List templates from local DB. Use /sync-all to refresh from Meta."""
    query = select(MessageTemplate).where(MessageTemplate.org_id == current_user.org_id)
    if status_filter:
        try:
            ts = TemplateStatus(status_filter.upper())
            query = query.where(MessageTemplate.status == ts)
        except ValueError:
            pass
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    current_user: OrgAdmin,
    db: DbDep,
) -> MessageTemplate:
    result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.id == template_id,
            MessageTemplate.org_id == current_user.org_id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return t


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    current_user: OrgAdmin,
    db: DbDep,
) -> MessageTemplate:
    """Update template components on Meta and locally.

    Note: Meta only allows updating components. Name, category, and language cannot
    be changed — delete and re-create the template if you need to change those.
    """
    t, waba = await _get_template_and_waba(template_id, current_user.org_id, db)

    if body.components is not None:
        if not t.meta_template_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Template has no Meta ID yet — it may still be pending submission.",
            )
        client = build_client(waba.access_token)
        try:
            await client.update_template(
                template_id=t.meta_template_id,
                components=body.components,
            )
        except MetaAPIError as exc:
            raise _meta_error_to_http(exc)
        t.components = body.components  # type: ignore[assignment]
        logger.info("template.updated", template_id=str(template_id), meta_id=t.meta_template_id)

    # Allow manual status/rejection_reason override (e.g. for test environments)
    if body.rejection_reason is not None:
        t.rejection_reason = body.rejection_reason  # type: ignore[assignment]
    if body.status is not None:
        try:
            t.status = TemplateStatus(body.status.upper())  # type: ignore[assignment]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status: {body.status}",
            )

    await db.commit()
    await db.refresh(t)
    return t


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    current_user: OrgAdmin,
    db: DbDep,
) -> None:
    """Delete a template from Meta and the local DB."""
    t, waba = await _get_template_and_waba(template_id, current_user.org_id, db)

    # Delete from Meta (best-effort — if it's not on Meta yet, still delete locally)
    if t.meta_template_id:
        client = build_client(waba.access_token)
        try:
            await client.delete_template(
                waba_id=waba.waba_id,
                template_name=t.name,
                template_id=t.meta_template_id,
            )
            logger.info("template.deleted_from_meta", name=t.name, meta_id=t.meta_template_id)
        except MetaAPIError as exc:
            logger.warning("template.meta_delete_failed", name=t.name, error=str(exc))
            # Still delete locally even if Meta fails (template may have already been deleted on Meta)

    await db.delete(t)
    await db.commit()


@router.post("/{template_id}/sync", response_model=TemplateResponse)
async def sync_template(
    template_id: uuid.UUID,
    current_user: OrgAdmin,
    db: DbDep,
) -> MessageTemplate:
    """Pull the latest status for this template from Meta and update the local record.

    Useful after submission — Meta typically approves/rejects within minutes.
    """
    t, waba = await _get_template_and_waba(template_id, current_user.org_id, db)

    client = build_client(waba.access_token)
    try:
        templates = await client.get_templates(waba.waba_id)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    meta_t = next(
        (m for m in templates if m.get("name") == t.name and m.get("language") == t.language),
        None,
    )
    if meta_t:
        _apply_meta_status(t, meta_t)
        logger.info("template.synced", name=t.name, status=t.status)
    else:
        logger.warning("template.not_found_on_meta", name=t.name, language=t.language)

    await db.commit()
    await db.refresh(t)
    return t


@router.post("/sync-all", response_model=list[TemplateResponse])
async def sync_all_templates(
    body: dict,
    current_user: OrgAdmin,
    db: DbDep,
) -> list[MessageTemplate]:
    """Pull ALL templates from Meta for a WABA and upsert into the local DB.

    Body: { "waba_id": "<internal waba UUID>" }

    - Templates found on Meta but not in DB → inserted
    - Templates found in both → status/meta_id updated
    - Templates in DB but not on Meta → left unchanged (may have been submitted locally)
    """
    waba_id_str = body.get("waba_id", "")
    if not waba_id_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="waba_id is required")

    try:
        waba_uuid = uuid.UUID(waba_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="waba_id must be a valid UUID")

    waba_result = await db.execute(
        select(WabaAccount).where(
            WabaAccount.id == waba_uuid,
            WabaAccount.org_id == current_user.org_id,
        )
    )
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")

    client = build_client(waba.access_token)
    try:
        meta_templates = await client.get_templates(waba.waba_id)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    # Use PostgreSQL INSERT ... ON CONFLICT DO UPDATE to avoid any duplicate issues.
    # The unique constraint is on (org_id, name, language).
    for meta_t in meta_templates:
        name = meta_t.get("name", "")
        language = meta_t.get("language", "en")
        meta_id = meta_t.get("id")

        raw_category = meta_t.get("category", "UTILITY").upper()
        try:
            category = TemplateCategory(raw_category)
        except ValueError:
            category = TemplateCategory.UTILITY

        raw_status = meta_t.get("status", "PENDING").upper()
        try:
            tmpl_status = TemplateStatus(raw_status)
        except ValueError:
            tmpl_status = TemplateStatus.PENDING

        rejection_reason = meta_t.get("rejected_reason") or meta_t.get("rejection_reason")
        components = meta_t.get("components", [])

        stmt = pg_insert(MessageTemplate).values(
            id=uuid.uuid4(),
            org_id=current_user.org_id,
            waba_id=waba_uuid,
            name=name,
            language=language,
            category=category,
            status=tmpl_status,
            components=components,
            meta_template_id=meta_id,
            rejection_reason=rejection_reason,
        ).on_conflict_do_update(
            constraint="uq_template_org_name_lang",
            set_={
                "meta_template_id": meta_id,
                "category": category,
                "status": tmpl_status,
                "components": components,
                "rejection_reason": rejection_reason,
                "waba_id": waba_uuid,
            },
        )
        await db.execute(stmt)

    await db.commit()

    logger.info("template.sync_all", waba_id=str(waba_uuid), meta_count=len(meta_templates))

    # Return all templates for this WABA
    final_result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.org_id == current_user.org_id,
            MessageTemplate.waba_id == waba_uuid,
        )
    )
    return list(final_result.scalars().all())

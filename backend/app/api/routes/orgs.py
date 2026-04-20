"""Organization CRUD routes (super_admin only for create/delete)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, OrgAdmin, SuperAdmin
from app.models.org import Organization
from app.schemas.common import MessageResponse
from app.schemas.org import OrgCreate, OrgRead, OrgSuspend, OrgUpdate

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("", response_model=list[OrgRead])
async def list_orgs(
    _: SuperAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrgRead]:
    """List all organizations (super_admin only)."""
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    return [OrgRead.model_validate(o) for o in result.scalars().all()]


@router.post("", response_model=OrgRead, status_code=201)
async def create_org(
    payload: OrgCreate,
    _: SuperAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgRead:
    """Create a new organization (super_admin only)."""
    taken = await db.execute(select(Organization).where(Organization.slug == payload.slug))
    if taken.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")
    org = Organization(**payload.model_dump())
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return OrgRead.model_validate(org)


@router.get("/me", response_model=OrgRead)
async def get_my_org(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgRead:
    """Return the current user's organization."""
    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrgRead.model_validate(org)


@router.get("/{org_id}", response_model=OrgRead)
async def get_org(
    org_id: uuid.UUID,
    _: SuperAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgRead:
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrgRead.model_validate(org)


@router.patch("/{org_id}", response_model=OrgRead)
async def update_org(
    org_id: uuid.UUID,
    payload: OrgUpdate,
    current_user: OrgAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgRead:
    """Org admins can update their own org; super_admin can update any."""
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    from app.models.user import UserRole
    if current_user.role != UserRole.super_admin and current_user.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return OrgRead.model_validate(org)


@router.post("/{org_id}/suspend", response_model=MessageResponse)
async def suspend_org(
    org_id: uuid.UUID,
    payload: OrgSuspend,
    _: SuperAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    org.is_suspended = True
    org.suspension_reason = payload.reason
    await db.commit()
    return MessageResponse(message="Organization suspended")


@router.post("/{org_id}/unsuspend", response_model=MessageResponse)
async def unsuspend_org(
    org_id: uuid.UUID,
    _: SuperAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    org.is_suspended = False
    org.suspension_reason = None
    await db.commit()
    return MessageResponse(message="Organization unsuspended")

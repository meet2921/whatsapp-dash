"""User management routes."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, OrgAdmin
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(
    current_user: OrgAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserRead]:
    """List users in the current org (super_admin sees all)."""
    if current_user.role == UserRole.super_admin:
        result = await db.execute(select(User).order_by(User.created_at.desc()))
    else:
        result = await db.execute(
            select(User)
            .where(User.org_id == current_user.org_id)
            .order_by(User.created_at.desc())
        )
    return [UserRead.model_validate(u) for u in result.scalars().all()]


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    current_user: OrgAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    """Create a user in the current org."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        org_id=current_user.org_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Can only read users in own org (unless super_admin)
    if current_user.role != UserRole.super_admin and user.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current_user: OrgAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.role != UserRole.super_admin and user.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.delete("/{user_id}", response_model=MessageResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: OrgAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Soft-delete: set is_active=False."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.role != UserRole.super_admin and user.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    user.is_active = False
    await db.commit()
    return MessageResponse(message="User deactivated")
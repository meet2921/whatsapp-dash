"""Authentication service: register, login, token refresh."""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.org import Organization
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

def _make_refresh_token(user_id: uuid.UUID) -> str:
    return create_access_token(
        subject=str(user_id),
        extra={"type": "refresh"},
    )


def _slug_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:100] or "org"


async def register(payload: RegisterRequest, db: AsyncSession) -> TokenResponse:
    """Create org + org_admin user + wallet, return tokens."""
    # Ensure email is unique
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Derive slug
    slug = payload.org_slug or _slug_from_name(payload.org_name)
    # Ensure slug is unique — append short uuid suffix if taken
    taken = await db.execute(select(Organization).where(Organization.slug == slug))
    if taken.scalar_one_or_none():
        slug = f"{slug}-{str(uuid.uuid4())[:8]}"

    org = Organization(name=payload.org_name, slug=slug)
    db.add(org)
    await db.flush()  # get org.id before user insert

    user = User(
        org_id=org.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.org_admin,
    )
    db.add(user)

    wallet = Wallet(org_id=org.id)
    db.add(wallet)

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(
        subject=str(user.id),
        extra={"org_id": str(org.id), "role": user.role.value},
    )
    refresh_token = _make_refresh_token(user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def login(payload: LoginRequest, db: AsyncSession) -> TokenResponse:
    """Verify credentials, update last_login, return tokens."""
    from fastapi import HTTPException, status

    result = await db.execute(
        select(User).where(User.email == payload.email, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user.last_login = datetime.now(timezone.utc)  # type: ignore[assignment]
    await db.commit()

    access_token = create_access_token(
        subject=str(user.id),
        extra={"org_id": str(user.org_id), "role": user.role.value},
    )
    refresh_token = _make_refresh_token(user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def refresh(refresh_token: str, db: AsyncSession) -> TokenResponse:
    """Validate a refresh token and issue a new access + refresh pair."""
    from fastapi import HTTPException, status
    from app.core.security import decode_token

    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(
        subject=str(user.id),
        extra={"org_id": str(user.org_id), "role": user.role.value},
    )
    new_refresh = _make_refresh_token(user.id)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh)

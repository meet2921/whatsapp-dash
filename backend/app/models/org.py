"""Organization and Plan models."""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_fee: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    msg_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organizations: Mapped[list["Organization"]] = relationship("Organization", back_populates="plan")


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True
    )
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Kolkata")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped["Plan | None"] = relationship("Plan", back_populates="organizations")
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")  # type: ignore[name-defined]
    wallet: Mapped["Wallet | None"] = relationship("Wallet", back_populates="organization", uselist=False)  # type: ignore[name-defined]

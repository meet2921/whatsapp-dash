"""WhatsApp Business account, phone numbers, and message templates."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid


class TemplateCategory(str, enum.Enum):
    MARKETING = "MARKETING"
    UTILITY = "UTILITY"
    AUTHENTICATION = "AUTHENTICATION"


class TemplateStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"


class WabaAccount(Base, TimestampMixin):
    __tablename__ = "waba_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    waba_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet-encrypted at rest
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    # Meta WABA fields
    business_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Meta Business Account ID
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timezone_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Meta timezone ID
    message_template_namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_review_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # APPROVED | PENDING | REJECTED

    phone_numbers: Mapped[list["PhoneNumber"]] = relationship("PhoneNumber", back_populates="waba_account")
    templates: Mapped[list["MessageTemplate"]] = relationship("MessageTemplate", back_populates="waba_account")


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    waba_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waba_accounts.id"), nullable=False
    )
    phone_number_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)  # GREEN, YELLOW, RED
    messaging_limit: Mapped[str | None] = mapped_column(String(50), nullable=True)  # TIER_1K, TIER_10K, TIER_100K
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Meta phone number fields
    code_verification_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # VERIFIED | NOT_VERIFIED
    platform_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # CLOUD_API | ON_PREMISE
    throughput_level: Mapped[str | None] = mapped_column(String(50), nullable=True)  # STANDARD | HIGH
    account_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)  # SANDBOX | LIVE
    name_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # APPROVED | PENDING | etc.
    last_onboarded_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    waba_account: Mapped["WabaAccount"] = relationship("WabaAccount", back_populates="phone_numbers")


class MessageTemplate(Base, TimestampMixin):
    __tablename__ = "message_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    waba_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waba_accounts.id"), nullable=False
    )
    meta_template_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[TemplateCategory] = mapped_column(
        Enum(TemplateCategory, name="templatecategory"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    status: Mapped[TemplateStatus] = mapped_column(
        Enum(TemplateStatus, name="templatestatus"), nullable=False, default=TemplateStatus.PENDING
    )
    components: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    waba_account: Mapped["WabaAccount"] = relationship("WabaAccount", back_populates="templates")

    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("org_id", "name", "language", name="uq_template_org_name_lang"),
        __import__("sqlalchemy").Index("ix_message_templates_org_status", "org_id", "status"),
    )


class LocalQrCode(Base):
    """Locally-stored QR codes for numbers that don't support Meta's QR code API."""
    __tablename__ = "local_qr_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_internal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("phone_numbers.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    prefilled_message: Mapped[str] = mapped_column(Text, nullable=False)
    deep_link_url: Mapped[str] = mapped_column(Text, nullable=False)
    qr_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=__import__("sqlalchemy").func.now(), nullable=False)

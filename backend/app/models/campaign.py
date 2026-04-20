"""Campaigns and campaign recipients."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class RecipientStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message_templates.id"), nullable=True
    )
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("phone_numbers.id"), nullable=True
    )
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaignstatus"),
        nullable=False,
        default=CampaignStatus.draft,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    read_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    actual_cost: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    template_variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    recipients: Mapped[list["CampaignRecipient"]] = relationship(
        "CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_campaigns_org_status", "org_id", "status"),)


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    template_variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="recipientstatus"),
        nullable=False,
        default=RecipientStatus.queued,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="recipients")

    __table_args__ = (Index("ix_campaign_recipients_campaign_status", "campaign_id", "status"),)

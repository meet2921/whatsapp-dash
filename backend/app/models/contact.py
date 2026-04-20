"""Contacts, tags, and segments."""
import uuid

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)  # E.164 format
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    is_opted_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lead_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    tags: Mapped[list["Tag"]] = relationship("Tag", secondary="contact_tags", back_populates="contacts")

    __table_args__ = (
        UniqueConstraint("org_id", "phone", name="uq_contact_org_phone"),
        Index("ix_contacts_org_opted_in", "org_id", "is_opted_in"),
        Index("ix_contacts_attributes", "attributes", postgresql_using="gin"),
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    contacts: Mapped[list["Contact"]] = relationship("Contact", secondary="contact_tags", back_populates="tags")

    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_tag_org_name"),)


class ContactTag(Base):
    __tablename__ = "contact_tags"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    filter_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    contact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

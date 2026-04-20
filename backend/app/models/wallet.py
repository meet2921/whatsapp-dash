"""Billing: credit rates, wallets, transactions, invoices."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, new_uuid


class TransactionType(str, enum.Enum):
    credit = "credit"
    debit = "debit"
    refund = "refund"
    adjustment = "adjustment"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rolled_back = "rolled_back"


class CreditRate(Base):
    __tablename__ = "credit_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    conversation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    meta_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    selling_price_inr: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    usd_to_inr_rate: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=83.5)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_credit_rates_type_country_active", "conversation_type", "country_code", "is_active"),
    )


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), unique=True, nullable=False
    )
    balance: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    low_balance_threshold: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=500)
    auto_recharge_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_recharge_amount: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    auto_recharge_trigger: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="wallet")  # type: ignore[name-defined]
    transactions: Mapped[list["WalletTransaction"]] = relationship(
        "WalletTransaction", back_populates="wallet"
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False
    )
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transactiontype"), nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transactionstatus"),
        nullable=False,
        default=TransactionStatus.pending,
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    balance_before: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")

    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_wallet_tx_org_idem"),
        Index("ix_wallet_transactions_org_created", "org_id", "created_at"),
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_inr: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    gst_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

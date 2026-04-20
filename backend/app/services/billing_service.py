"""Two-phase atomic billing service (Upgrade 2).

Phase 1 — RESERVE:
  Lock wallet row, check balance, INSERT pending transaction, UPDATE balance.

Phase 2a — CONFIRM:
  UPDATE transaction → confirmed.

Phase 2b — ROLLBACK:
  Refund balance, UPDATE transaction → rolled_back.

All balance math happens inside PostgreSQL transactions — no Python arithmetic
on fetched values to avoid race conditions.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import TransactionStatus, TransactionType, Wallet, WalletTransaction


async def reserve_credits(
    db: AsyncSession,
    org_id: uuid.UUID,
    amount: float,
    idempotency_key: str,
    description: str = "",
    message_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
) -> WalletTransaction:
    """Reserve credits (debit phase-1).  Raises 402 if insufficient balance."""
    # --- Lock wallet row -------------------------------------------------------
    result = await db.execute(
        select(Wallet).where(Wallet.org_id == org_id).with_for_update()
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

    balance_before = float(wallet.balance)
    if balance_before < amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient balance: {balance_before:.2f} < {amount:.2f}",
        )

    balance_after = balance_before - amount

    # --- Create pending transaction --------------------------------------------
    txn = WalletTransaction(
        org_id=org_id,
        wallet_id=wallet.id,
        type=TransactionType.debit,
        status=TransactionStatus.pending,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        description=description,
        idempotency_key=idempotency_key,
        message_id=message_id,
        campaign_id=campaign_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(txn)

    # --- Deduct balance --------------------------------------------------------
    wallet.balance = balance_after  # type: ignore[assignment]
    wallet.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

    await db.flush()
    logger.info(
        "billing.reserve",
        org_id=str(org_id),
        amount=amount,
        balance_after=balance_after,
        txn_id=str(txn.id),
    )
    return txn


async def confirm_credits(
    db: AsyncSession,
    txn: WalletTransaction,
) -> None:
    """Confirm a pending transaction → mark consumed."""
    txn.status = TransactionStatus.confirmed
    await db.flush()
    logger.info("billing.confirm", txn_id=str(txn.id))


async def rollback_credits(
    db: AsyncSession,
    txn: WalletTransaction,
) -> None:
    """Rollback a pending transaction → refund balance."""
    # Lock wallet and refund
    result = await db.execute(
        select(Wallet).where(Wallet.id == txn.wallet_id).with_for_update()
    )
    wallet = result.scalar_one()
    wallet.balance = float(wallet.balance) + float(txn.amount)  # type: ignore[assignment]
    wallet.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

    txn.status = TransactionStatus.rolled_back
    await db.flush()
    logger.warning("billing.rollback", txn_id=str(txn.id), refund=float(txn.amount))


async def get_credit_rate(
    db: AsyncSession,
    conversation_type: str,
    country_code: str,
    org_id: uuid.UUID | None = None,
) -> float:
    """Look up the selling price for a conversation type.

    First tries a per-org override, then falls back to the global rate.
    Returns 0.0 if no rate found (free — e.g. service conversations).
    """
    from app.models.wallet import CreditRate
    from sqlalchemy import and_, or_

    # Per-org override first
    if org_id:
        result = await db.execute(
            select(CreditRate).where(
                and_(
                    CreditRate.conversation_type == conversation_type,
                    CreditRate.country_code == country_code,
                    CreditRate.org_id == org_id,
                    CreditRate.is_active == True,
                )
            ).limit(1)
        )
        rate = result.scalar_one_or_none()
        if rate:
            return float(rate.selling_price_inr)

    # Global default
    result = await db.execute(
        select(CreditRate).where(
            and_(
                CreditRate.conversation_type == conversation_type,
                CreditRate.country_code == country_code,
                CreditRate.org_id.is_(None),
                CreditRate.is_active == True,
            )
        ).limit(1)
    )
    rate = result.scalar_one_or_none()
    return float(rate.selling_price_inr) if rate else 0.0

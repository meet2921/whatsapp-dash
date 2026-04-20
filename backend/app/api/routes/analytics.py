"""Analytics endpoints — live queries from the messages table.

GET /analytics/overview   — aggregate totals + rates
GET /analytics/daily      — per-day breakdown for last N days
"""
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.models.message import Conversation, Message, MessageDirection, MessageStatus

router = APIRouter(prefix="/analytics", tags=["Analytics"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


# ── helpers ───────────────────────────────────────────────────────────────────

def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_overview(
    current_user: CurrentUser,
    db: DbDep,
) -> dict:
    """Return aggregate message statistics for the current org."""
    org_id = current_user.org_id
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # ── outbound counts by status ─────────────────────────────────────────────
    outbound_q = (
        select(Message.status, func.count().label("cnt"))
        .where(
            Message.org_id == org_id,
            Message.direction == MessageDirection.outbound,
        )
        .group_by(Message.status)
    )
    rows = (await db.execute(outbound_q)).all()
    outbound_counts: dict[str, int] = {r.status.value: r.cnt for r in rows}

    total_sent = sum(outbound_counts.values())
    total_delivered = outbound_counts.get(MessageStatus.delivered.value, 0)
    total_read = outbound_counts.get(MessageStatus.read.value, 0)
    total_failed = outbound_counts.get(MessageStatus.failed.value, 0)

    # ── inbound count ─────────────────────────────────────────────────────────
    inbound_q = (
        select(func.count())
        .where(
            Message.org_id == org_id,
            Message.direction == MessageDirection.inbound,
        )
    )
    total_inbound: int = (await db.execute(inbound_q)).scalar_one()

    # ── distinct conversations ────────────────────────────────────────────────
    conv_q = (
        select(func.count())
        .where(Conversation.org_id == org_id)
    )
    total_conversations: int = (await db.execute(conv_q)).scalar_one()

    # ── today stats ───────────────────────────────────────────────────────────
    today_out_q = (
        select(Message.status, func.count().label("cnt"))
        .where(
            Message.org_id == org_id,
            Message.direction == MessageDirection.outbound,
            Message.created_at >= today_start,
        )
        .group_by(Message.status)
    )
    today_rows = (await db.execute(today_out_q)).all()
    today_counts: dict[str, int] = {r.status.value: r.cnt for r in today_rows}

    today_sent = sum(today_counts.values())
    today_delivered = today_counts.get(MessageStatus.delivered.value, 0)

    today_in_q = (
        select(func.count())
        .where(
            Message.org_id == org_id,
            Message.direction == MessageDirection.inbound,
            Message.created_at >= today_start,
        )
    )
    today_inbound: int = (await db.execute(today_in_q)).scalar_one()

    return {
        "total_messages_sent": total_sent,
        "total_messages_delivered": total_delivered,
        "total_messages_read": total_read,
        "total_messages_failed": total_failed,
        "total_inbound": total_inbound,
        "total_conversations": total_conversations,
        "delivery_rate": _pct(total_delivered, total_sent),
        "read_rate": _pct(total_read, total_sent),
        "today_sent": today_sent,
        "today_delivered": today_delivered,
        "today_inbound": today_inbound,
    }


# ── Daily breakdown ───────────────────────────────────────────────────────────

@router.get("/daily")
async def get_daily(
    current_user: CurrentUser,
    db: DbDep,
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    """Return a per-day message breakdown for the last *days* calendar days."""
    org_id = current_user.org_id
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # ── outbound per day per status ───────────────────────────────────────────
    out_q = (
        select(
            cast(Message.created_at, Date).label("day"),
            Message.status,
            func.count().label("cnt"),
        )
        .where(
            Message.org_id == org_id,
            Message.direction == MessageDirection.outbound,
            Message.created_at >= since,
        )
        .group_by(cast(Message.created_at, Date), Message.status)
        .order_by(cast(Message.created_at, Date))
    )
    out_rows = (await db.execute(out_q)).all()

    # ── inbound per day ───────────────────────────────────────────────────────
    in_q = (
        select(
            cast(Message.created_at, Date).label("day"),
            func.count().label("cnt"),
        )
        .where(
            Message.org_id == org_id,
            Message.direction == MessageDirection.inbound,
            Message.created_at >= since,
        )
        .group_by(cast(Message.created_at, Date))
        .order_by(cast(Message.created_at, Date))
    )
    in_rows = (await db.execute(in_q)).all()

    # ── assemble into date-keyed dict ─────────────────────────────────────────
    data: dict[str, dict] = {}

    def _ensure(d: date) -> dict:
        key = d.isoformat() if isinstance(d, date) else str(d)
        if key not in data:
            data[key] = {"date": key, "sent": 0, "delivered": 0, "read": 0, "failed": 0, "inbound": 0}
        return data[key]

    for row in out_rows:
        entry = _ensure(row.day)
        status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
        if status_val in ("sent", "delivered", "read", "failed"):
            entry[status_val] += row.cnt
        else:
            # queued / unknown — count toward sent total
            entry["sent"] += row.cnt

    for row in in_rows:
        entry = _ensure(row.day)
        entry["inbound"] += row.cnt

    # return sorted list
    return sorted(data.values(), key=lambda x: x["date"])

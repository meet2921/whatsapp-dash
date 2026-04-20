"""Global idempotency helpers — Redis fast-path + DB unique constraint fallback.

Key pattern:  idem:{namespace}:{sha256(parts)}
TTL:          86400 seconds (24 hours)

Usage:
    from app.core.idempotency import IdempotencyKey, check_and_set, clear

    key = IdempotencyKey.webhook("meta", entry_id, event_type)
    seen = await check_and_set(redis, key)
    if seen:
        return  # already processed
"""
import hashlib

import redis.asyncio as aioredis

IDEM_TTL = 86_400  # 24 hours


class IdempotencyKey:
    @staticmethod
    def webhook(source: str, entry_id: str, event_type: str) -> str:
        digest = hashlib.sha256(f"{source}:{entry_id}:{event_type}".encode()).hexdigest()
        return f"idem:webhook:{digest}"

    @staticmethod
    def message(org_id: str, phone: str, campaign_id: str, content_hash: str) -> str:
        digest = hashlib.sha256(
            f"{org_id}:{phone}:{campaign_id}:{content_hash}".encode()
        ).hexdigest()
        return f"idem:message:{digest}"

    @staticmethod
    def wallet_debit(org_id: str, message_id: str) -> str:
        digest = hashlib.sha256(f"{org_id}:{message_id}".encode()).hexdigest()
        return f"idem:billing_debit:{digest}"

    @staticmethod
    def wallet_credit(org_id: str, payment_id: str) -> str:
        digest = hashlib.sha256(f"{org_id}:{payment_id}".encode()).hexdigest()
        return f"idem:billing_credit:{digest}"


async def check_and_set(redis: aioredis.Redis, key: str, ttl: int = IDEM_TTL) -> bool:
    """Atomically check-and-set. Returns True if key was already seen (duplicate)."""
    result = await redis.set(key, "1", nx=True, ex=ttl)
    return result is None  # None means SET NX failed → key existed


async def clear(redis: aioredis.Redis, key: str) -> None:
    """Delete key to allow retry (call on failure path)."""
    await redis.delete(key)

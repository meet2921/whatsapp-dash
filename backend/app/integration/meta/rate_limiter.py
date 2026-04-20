"""Redis sliding-window rate limiter for Meta Cloud API.

Meta's hard limit: 80 messages/second per phone number.
Exceeding it returns HTTP 429 with error code 130429.

We enforce it client-side to avoid wasting a round-trip to Meta.

Algorithm: Redis sorted set sliding window
  Key:   meta:rate:{phone_number_id}
  Score: current timestamp in milliseconds
  Member: "<timestamp_ms>:<random_suffix>"   (unique per request)
  TTL:   2 seconds (auto-cleanup)

Usage:
    from app.integration.meta.rate_limiter import MetaRateLimiter

    limiter = MetaRateLimiter(redis_client)
    allowed = await limiter.acquire("1234567890123456")
    if not allowed:
        raise MetaRateLimitError(429, {"error": {"message": "local rate limit"}})
"""
import time
import uuid

import redis.asyncio as aioredis
from loguru import logger


META_SEND_LIMIT = 80     # messages per second
WINDOW_MS = 1_000        # sliding window = 1 second in ms
KEY_TTL_S = 5            # Redis key expiry (generous — cleans up automatically)


class MetaRateLimiter:
    """Per-phone-number sliding window rate limiter backed by Redis."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def acquire(self, phone_number_id: str) -> bool:
        """Attempt to acquire a send slot.

        Returns:
            True  — slot acquired, proceed with send
            False — rate limit hit, caller should back off
        """
        key = f"meta:rate:{phone_number_id}"
        now_ms = int(time.time() * 1_000)
        window_start = now_ms - WINDOW_MS
        member = f"{now_ms}:{uuid.uuid4().hex[:8]}"

        try:
            pipe = self._redis.pipeline(transaction=True)
            # Remove entries outside the current window
            pipe.zremrangebyscore(key, "-inf", window_start)
            # Count entries inside the window (before this request)
            pipe.zcard(key)
            # Add this request to the window
            pipe.zadd(key, {member: now_ms})
            # Ensure key expires (no orphaned memory)
            pipe.expire(key, KEY_TTL_S)
            results = await pipe.execute()

            count_before = results[1]  # zcard result
            if count_before >= META_SEND_LIMIT:
                # Over limit — remove what we just added and signal caller
                await self._redis.zrem(key, member)
                logger.warning(
                    "meta.rate_limit_hit",
                    phone_number_id=phone_number_id,
                    count=count_before,
                    limit=META_SEND_LIMIT,
                )
                return False

            return True

        except Exception as exc:
            # Redis failure — fail open (better to risk a Meta 429 than drop a message)
            logger.warning("meta.rate_limiter.redis_error", error=str(exc))
            return True

    async def current_rate(self, phone_number_id: str) -> int:
        """Return the current message count in the sliding window (for monitoring)."""
        key = f"meta:rate:{phone_number_id}"
        now_ms = int(time.time() * 1_000)
        window_start = now_ms - WINDOW_MS
        try:
            await self._redis.zremrangebyscore(key, "-inf", window_start)
            return await self._redis.zcard(key)
        except Exception:
            return 0

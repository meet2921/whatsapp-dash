"""FastAPI-compatible factory for MetaClient.

Usage in a route:
    from app.integration.meta.deps import get_meta_client

    @router.post("/send")
    async def send(
        waba_id: uuid.UUID,
        current_user: CurrentUser,
        db: DbDep,
        meta: Annotated[MetaClient, Depends(get_meta_client_for_waba(...))],
    ): ...

Because the access token comes from the DB (per org/WABA), we expose a
plain factory function rather than a bare Depends — callers fetch the WABA
first, then call build_client().
"""
from app.integration.meta.client import MetaClient
from app.integration.meta.rate_limiter import MetaRateLimiter


def build_client(access_token: str, redis=None) -> MetaClient:
    """Create a MetaClient wired with an optional rate limiter.

    Args:
        access_token: org's System User Token from waba_accounts.access_token
        redis:        live Redis connection — pass one to enforce 80 msg/s limit.
                      If None, rate limiting is skipped (fails open).
    """
    limiter = MetaRateLimiter(redis) if redis is not None else None
    return MetaClient(access_token=access_token, rate_limiter=limiter)

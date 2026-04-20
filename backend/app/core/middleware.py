"""Request-context and tenant-context middleware.

RequestContextMiddleware:
  - Generates a unique request_id per request
  - Sets request_id + org_id into ContextVars (picked up by every log line)
  - Adds X-Request-ID response header

TenantMiddleware is intentionally lightweight — org_id extraction from JWT
happens in the auth dependency (get_current_user) because not all endpoints
require authentication. The middleware only propagates org_id once it's set.
"""
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import org_id_var, request_id_var


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Inject request_id into ContextVar and response headers; log every request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = str(uuid.uuid4())
        token = request_id_var.set(req_id)

        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
        except Exception:
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status_code=getattr(response, "status_code", 500),
                duration_ms=round(duration_ms, 2),
            )
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = req_id
        return response


class OrgContextMiddleware(BaseHTTPMiddleware):
    """Extract org_id from a decoded JWT claim and store it in ContextVar.

    This runs after authentication — if the request has no auth header it's
    a no-op (org_id stays as the default "-").
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Auth dependency sets request.state.org_id after JWT decode.
        # We read it here (post-route) only for logging; actual enforcement
        # is in get_current_user dependency.
        response = await call_next(request)
        org_id = getattr(request.state, "org_id", None)
        if org_id:
            org_id_var.set(str(org_id))
        return response

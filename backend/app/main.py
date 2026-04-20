"""FastAPI application factory.

Wires together:
  - Structured logging (loguru)
  - OpenTelemetry tracing → Jaeger/OTLP
  - Prometheus metrics (prometheus-fastapi-instrumentator)
  - CORS
  - RequestContext + OrgContext middleware
  - All API routers under /api/v1
  - Health + readiness endpoints
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.router import api_router
from app.api.routes.inbox import router as inbox_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import OrgContextMiddleware, RequestContextMiddleware


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hooks."""
    setup_logging(
        log_level="DEBUG" if settings.DEBUG else "INFO",
        log_file=None,  # stdout only inside Docker; add path for VM deploys
    )
    _setup_tracing()
    yield
    # Graceful shutdown: close DB engine pool
    from app.core.database import engine
    await engine.dispose()


def _setup_tracing() -> None:
    """Configure OpenTelemetry → OTLP (Jaeger in dev, Tempo in prod)."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        provider = TracerProvider()
        otlp_exporter = OTLPSpanExporter(
            endpoint="http://jaeger:4317",
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor().instrument()
        # SQLAlchemy instrumentation wired after engine is created
    except Exception:
        pass  # Tracing is optional in dev — never crash the app over it


# ── App factory ────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        description="Multi-tenant WhatsApp engagement SaaS — TierceMsg",
        version="0.1.0",
        docs_url="/docs" if settings.APP_ENV != "production" else None,
        redoc_url="/redoc" if settings.APP_ENV != "production" else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost first) ───────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(OrgContextMiddleware)

    # ── Prometheus metrics at /metrics ────────────────────────────────────────
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/ready", "/metrics"],
    ).instrument(application).expose(application, endpoint="/metrics")

    # ── API routes ─────────────────────────────────────────────────────────────
    application.include_router(api_router, prefix=settings.API_PREFIX)
    # WebSocket routes (no /api/v1 prefix — browsers connect directly)
    application.include_router(inbox_router)

    # ── Utility endpoints ─────────────────────────────────────────────────────
    @application.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok"}

    @application.get("/ready", tags=["ops"], include_in_schema=False)
    async def ready() -> dict:
        """Check DB + Redis connectivity."""
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal
        import redis.asyncio as aioredis

        checks: dict[str, str] = {}

        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:
            checks["db"] = f"error: {exc}"

        try:
            r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"

        overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
        return {"status": overall, **checks}

    return application


app = create_app()

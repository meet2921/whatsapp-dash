"""Structured JSON logging via loguru.

Every log line carries: timestamp, level, message, request_id, org_id, module, function.
Call `setup_logging()` once at app startup.
"""
import logging
import sys
from contextvars import ContextVar

from loguru import logger

# ContextVars — injected by middleware per-request
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
org_id_var: ContextVar[str] = ContextVar("org_id", default="-")


def _json_formatter(record: dict) -> str:
    """Produce a single-line JSON log record."""
    import json
    from datetime import timezone

    payload = {
        "timestamp": record["time"].astimezone(timezone.utc).isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "request_id": request_id_var.get("-"),
        "org_id": org_id_var.get("-"),
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }
    if record["exception"]:
        payload["exception"] = record["exception"]
    payload.update(record["extra"])
    return json.dumps(payload) + "\n"


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, sqlalchemy, celery) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Configure loguru as the single logging backend."""
    logger.remove()

    logger.add(
        sys.stdout,
        level=log_level,
        format='{{"timestamp": "{time:YYYY-MM-DD HH:mm:ss}", "level": "{level}", "message": "{message}"}}',
        colorize=False,
        backtrace=False,
        diagnose=False,
    )

    if log_file:
        logger.add(
            log_file,
            level=log_level,
            format='{{"timestamp": "{time:YYYY-MM-DD HH:mm:ss}", "level": "{level}", "message": "{message}"}}',
            rotation="100 MB",
            retention="30 days",
            compression="gz",
            backtrace=False,
            diagnose=False,
        )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine", "celery"):
        logging.getLogger(name).handlers = [_InterceptHandler()]
        logging.getLogger(name).propagate = False

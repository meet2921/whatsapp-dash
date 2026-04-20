"""Celery application with 6 segregated queues (Upgrade 3).

Queue strategy:
  campaign_queue  — bulk dispatch (high volume, rate-limited)
  message_queue   — single sends (low latency)
  webhook_queue   — inbound Meta/Razorpay events (dedicated, never starved)
  billing_queue   — payment events, invoice gen (prefetch=1, serial)
  media_queue     — S3 upload + metadata extraction (CPU/IO-bound)
  analytics_queue — stats aggregation (lowest priority)
"""
from celery import Celery
from kombu import Exchange, Queue

from app.core.config import settings

# ── App ────────────────────────────────────────────────────────────────────────
celery_app = Celery(
    "wmsg",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.webhook_tasks",
        "app.tasks.message_tasks",
        "app.tasks.campaign_tasks",
        "app.tasks.billing_tasks",
        "app.tasks.media_tasks",
        "app.tasks.analytics_tasks",
    ],
)

# ── Queues / Exchanges ─────────────────────────────────────────────────────────
default_exchange = Exchange("wmsg", type="direct")

celery_app.conf.task_queues = (
    Queue("campaign_queue",  default_exchange, routing_key="campaign"),
    Queue("message_queue",   default_exchange, routing_key="message"),
    Queue("webhook_queue",   default_exchange, routing_key="webhook"),
    Queue("billing_queue",   default_exchange, routing_key="billing"),
    Queue("media_queue",     default_exchange, routing_key="media"),
    Queue("analytics_queue", default_exchange, routing_key="analytics"),
)

celery_app.conf.task_default_queue = "message_queue"
celery_app.conf.task_default_exchange = "wmsg"
celery_app.conf.task_default_routing_key = "message"

# ── Per-queue routing ──────────────────────────────────────────────────────────
celery_app.conf.task_routes = {
    "app.tasks.webhook_tasks.*":   {"queue": "webhook_queue"},
    "app.tasks.message_tasks.*":   {"queue": "message_queue"},
    "app.tasks.campaign_tasks.*":  {"queue": "campaign_queue"},
    "app.tasks.billing_tasks.*":   {"queue": "billing_queue"},
    "app.tasks.media_tasks.*":     {"queue": "media_queue"},
    "app.tasks.analytics_tasks.*": {"queue": "analytics_queue"},
}

# ── Retry policies (Upgrade 3) ─────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability
    task_acks_late=True,          # ack only after task completes
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=4,  # overridden per-worker via CLI

    # Result expiry
    result_expires=3600,

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # RedBeat scheduler backend
    redbeat_redis_url=settings.REDIS_URL,

    # Beat schedule — Phase 2
    beat_schedule={
        "retry-failed-webhooks": {
            "task": "app.tasks.webhook_tasks.retry_failed_webhooks",
            "schedule": 60.0,  # every 60 seconds
        },
    },
)

# ── Per-task retry defaults (set via @celery_app.task decorator in task files)
RETRY_POLICIES = {
    "campaign": {"max_retries": 3,  "default_retry_delay": 30,   "autoretry_for": (Exception,)},
    "message":  {"max_retries": 5,  "default_retry_delay": 10,   "autoretry_for": (Exception,)},
    "webhook":  {"max_retries": 5,  "default_retry_delay": 60,   "autoretry_for": (Exception,)},
    "billing":  {"max_retries": 3,  "default_retry_delay": 60,   "autoretry_for": (Exception,)},
    "media":    {"max_retries": 3,  "default_retry_delay": 30,   "autoretry_for": (Exception,)},
    "analytics":{"max_retries": 2,  "default_retry_delay": 120,  "autoretry_for": (Exception,)},
}

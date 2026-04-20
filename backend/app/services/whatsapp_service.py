"""WhatsApp service — thin facade over app.integration.meta.

All real logic lives in the integration layer:
  app/integration/meta/client.py   → MetaClient (HTTP, retry, rate limit)
  app/integration/meta/webhook.py  → MetaWebhook (verify + parse)
  app/integration/meta/types.py    → SendResult, InboundMessage, etc.

This module re-exports the integration types so existing callers
(routes/messages.py, tasks/webhook_tasks.py) don't need to change imports.
"""

# Re-export everything callers need
from app.integration.meta.client import MetaClient as WhatsAppService  # backward-compat alias
from app.integration.meta.exceptions import (
    MetaAPIError,
    MetaAuthError,
    MetaRateLimitError,
    MetaTransientError,
    MetaWebhookSignatureError,
)
from app.integration.meta.types import InboundMessage, ParsedWebhookPayload, SendResult, StatusUpdate
from app.integration.meta.webhook import MetaWebhook

__all__ = [
    # Backward-compat alias (routes import WhatsAppService)
    "WhatsAppService",
    # Exceptions
    "MetaAPIError",
    "MetaAuthError",
    "MetaRateLimitError",
    "MetaTransientError",
    "MetaWebhookSignatureError",
    # Types
    "InboundMessage",
    "ParsedWebhookPayload",
    "SendResult",
    "StatusUpdate",
    # Webhook utilities
    "MetaWebhook",
]

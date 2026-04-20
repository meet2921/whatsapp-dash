"""Meta Cloud API integration layer.

Public surface — import only from here:

    from app.integration.meta import MetaClient, MetaWebhook
    from app.integration.meta.exceptions import MetaAPIError, MetaAuthError, MetaRateLimitError
    from app.integration.meta.types import InboundMessage, StatusUpdate, SendResult

Design rules:
  - No SQLAlchemy / FastAPI imports in this package (pure I/O layer)
  - All methods are async
  - Raises typed exceptions — callers decide how to handle
  - Rate limiter is optional (fails open — never block a send due to Redis down)
"""
from app.integration.meta.client import MetaClient
from app.integration.meta.provisioning import MetaProvisioning, get_provisioning_client
from app.integration.meta.webhook import MetaWebhook

__all__ = ["MetaClient", "MetaWebhook", "MetaProvisioning", "get_provisioning_client"]

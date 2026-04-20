"""Central API router — registers all v1 route modules."""
from fastapi import APIRouter

from app.api.routes import analytics, auth, campaigns, contacts, messages, orgs, templates, users, waba, webhook_mgmt, webhooks

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(orgs.router)
api_router.include_router(users.router)
api_router.include_router(waba.router)
api_router.include_router(templates.router)
api_router.include_router(messages.router)
api_router.include_router(webhooks.router)
api_router.include_router(analytics.router)
api_router.include_router(webhook_mgmt.router)
api_router.include_router(contacts.router)
api_router.include_router(campaigns.router)

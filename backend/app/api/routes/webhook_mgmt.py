"""Webhook subscription management for WABA accounts.

GET  /webhook-config/status                — subscription status for all WABAs
POST /webhook-config/{waba_id}/subscribe   — subscribe app to WABA webhooks
POST /webhook-config/{waba_id}/unsubscribe — unsubscribe app from WABA webhooks
"""
import uuid
from typing import Annotated, TypeAlias

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import OrgAdmin
from app.integration.meta.exceptions import MetaAPIError, MetaAuthError
from app.integration.meta.provisioning import META_BASE_URL, REQUEST_TIMEOUT, get_provisioning_client
from app.models.whatsapp import WabaAccount

router = APIRouter(prefix="/webhook-config", tags=["Webhook Config"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


async def _get_waba(waba_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> WabaAccount:
    result = await db.execute(
        select(WabaAccount).where(WabaAccount.id == waba_id, WabaAccount.org_id == org_id)
    )
    waba = result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")
    return waba


@router.get("/status")
async def get_webhook_status(current_user: OrgAdmin, db: DbDep) -> list[dict]:
    """Return webhook subscription status for every WABA in this org."""
    result = await db.execute(
        select(WabaAccount).where(WabaAccount.org_id == current_user.org_id)
    )
    wabas = list(result.scalars().all())
    provisioning = get_provisioning_client()
    statuses: list[dict] = []

    for waba in wabas:
        subscribed_apps: list[dict] = []
        error_msg: str | None = None
        try:
            subscribed_apps = await provisioning.get_subscribed_apps(waba.waba_id, waba.access_token)
        except MetaAuthError:
            error_msg = "Token invalid or expired"
        except MetaAPIError as exc:
            error_msg = str(exc)

        fields: list[str] = []
        for app in subscribed_apps:
            fields.extend(app.get("whatsapp_business_api_data", {}).get("fields", []))

        statuses.append({
            "waba_id": str(waba.id),
            "meta_waba_id": waba.waba_id,
            "business_name": waba.business_name,
            "is_subscribed": len(subscribed_apps) > 0,
            "subscribed_apps": subscribed_apps,
            "subscribed_fields": list(set(fields)),
            "error": error_msg,
        })

    return statuses


@router.post("/{waba_id}/subscribe")
async def subscribe_webhooks(waba_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> dict:
    """Subscribe app to receive webhooks for this WABA."""
    waba = await _get_waba(waba_id, current_user.org_id, db)
    provisioning = get_provisioning_client()
    try:
        success = await provisioning.subscribe_app_to_waba(waba.waba_id, waba.access_token)
    except MetaAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Meta token invalid or expired: {exc}")
    except MetaAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Meta API error: {exc}")
    logger.info("webhook.subscribed", meta_waba_id=waba.waba_id)
    return {"success": success, "meta_waba_id": waba.waba_id, "action": "subscribe"}


@router.post("/{waba_id}/unsubscribe")
async def unsubscribe_webhooks(waba_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> dict:
    """Unsubscribe app from webhooks for this WABA."""
    waba = await _get_waba(waba_id, current_user.org_id, db)
    url = f"{META_BASE_URL}/{waba.waba_id}/subscribed_apps"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.delete(url, params={"access_token": waba.access_token})
    body: dict = resp.json() if resp.content else {}
    if resp.status_code in (401, 403):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Meta access token invalid or expired")
    if resp.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Meta API error: {body.get('error', {}).get('message', str(body))}")
    logger.info("webhook.unsubscribed", meta_waba_id=waba.waba_id)
    return {"success": body.get("success", True), "meta_waba_id": waba.waba_id, "action": "unsubscribe"}

"""WebSocket inbox — real-time conversation updates.

WS /ws/inbox/{org_id}?token={jwt}

On connect:
  1. Validate JWT from query param.
  2. Verify caller's org_id matches path org_id (or caller is super_admin).
  3. Subscribe to Redis channel: inbox:{org_id}
  4. Forward all messages to the WebSocket client.

The Redis channel is published to by:
  - messages.py: on outbound send
  - webhook_tasks.py: on inbound message or status update
"""
import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from loguru import logger

from app.core.config import settings
from app.core.redis_client import get_redis
from app.core.security import decode_token

router = APIRouter(tags=["Inbox"])


@router.websocket("/ws/inbox/{org_id}")
async def inbox_websocket(
    websocket: WebSocket,
    org_id: uuid.UUID,
    token: str = Query(...),
) -> None:
    """WebSocket endpoint for real-time inbox updates."""

    # --- Auth via query-param JWT -----------------------------------------------
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4001)
        return

    caller_org_id = payload.get("org_id")
    caller_role = payload.get("role", "")

    # Super admins can listen on any org; normal users only their own
    if caller_role != "super_admin" and caller_org_id != str(org_id):
        await websocket.close(code=4003)
        return

    await websocket.accept()
    channel = f"inbox:{org_id}"
    logger.info("ws.inbox.connected", org_id=str(org_id))

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    try:
        # Run send loop and ping-pong concurrently
        send_task = asyncio.create_task(_redis_to_ws(pubsub, websocket, org_id))
        ping_task = asyncio.create_task(_ping_loop(websocket))

        done, pending = await asyncio.wait(
            {send_task, ping_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws.inbox.error", org_id=str(org_id), error=str(exc))
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            pass
        logger.info("ws.inbox.disconnected", org_id=str(org_id))


async def _redis_to_ws(pubsub, websocket: WebSocket, org_id: uuid.UUID) -> None:
    """Forward Redis pub/sub messages to the WebSocket."""
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = message["data"]
        try:
            await websocket.send_text(data if isinstance(data, str) else data.decode())
        except Exception:
            break


async def _ping_loop(websocket: WebSocket) -> None:
    """Send a keep-alive ping every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        try:
            await websocket.send_text(json.dumps({"event": "ping"}))
        except Exception:
            break

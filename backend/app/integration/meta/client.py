"""Meta Cloud API client — production-grade async HTTP client.

Design:
  - One MetaClient instance per request, initialised with the org's access_token
  - All network calls go through _post() / _get() which handle:
      Tenacity retry   → 5xx + network errors only (not 4xx — those are bugs)
      Error mapping    → HTTP status + Meta error code → typed exception
      Structured logging → every call logged with phone_number_id + latency
  - Rate limiter (optional) → pass a MetaRateLimiter to enforce 80 msg/s
  - No state stored — safe to create / discard per request

Meta Cloud API base:
  https://graph.facebook.com/v22.0/

Key endpoints:
  POST /{phone_number_id}/messages       → send any message type
  GET  /{waba_id}/phone_numbers          → list registered phone numbers
  GET  /{waba_id}/message_templates      → list templates
  POST /{waba_id}/message_templates      → submit new template
  GET  /{phone_number_id}/media          → get media upload URL
  POST /media                            → upload media
  GET  /{media_id}                       → fetch media download URL
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.integration.meta.exceptions import (
    MetaAPIError,
    MetaAuthError,
    MetaRateLimitError,
    MetaTransientError,
)
from app.integration.meta.rate_limiter import MetaRateLimiter
from app.integration.meta.types import SendResult

META_API_VERSION = "v25.0"
META_BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"

# HTTP timeout per request (seconds)
REQUEST_TIMEOUT = 15.0


class MetaClient:
    """Async Meta Cloud API client.

    Args:
        access_token: System User Token from Meta Business Manager
        rate_limiter: Optional MetaRateLimiter — pass one to enforce 80 msg/s
    """

    def __init__(
        self,
        access_token: str,
        rate_limiter: MetaRateLimiter | None = None,
    ) -> None:
        self._token = access_token
        self._rate_limiter = rate_limiter
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    # ── Internal HTTP layer ────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(MetaTransientError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{META_BASE_URL}/{path}"
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        body = self._parse_body(resp)
        self._raise_for_error(resp.status_code, body, path, elapsed_ms)

        logger.debug(
            "meta.post.ok",
            path=path,
            status=resp.status_code,
            elapsed_ms=elapsed_ms,
        )
        return body

    @retry(
        retry=retry_if_exception_type(MetaTransientError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{META_BASE_URL}/{path}"
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers, params=params or {})
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        body = self._parse_body(resp)
        self._raise_for_error(resp.status_code, body, path, elapsed_ms)

        logger.debug(
            "meta.get.ok",
            path=path,
            status=resp.status_code,
            elapsed_ms=elapsed_ms,
        )
        return body

    async def _delete(self, path: str, params: dict | None = None) -> dict:
        url = f"{META_BASE_URL}/{path}"
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.delete(url, headers=self._headers, params=params or {})
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        body = self._parse_body(resp)
        self._raise_for_error(resp.status_code, body, path, elapsed_ms)

        logger.debug("meta.delete.ok", path=path, status=resp.status_code, elapsed_ms=elapsed_ms)
        return body

    @staticmethod
    def _parse_body(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    @staticmethod
    def _raise_for_error(status_code: int, body: dict, path: str, elapsed_ms: int) -> None:
        if status_code < 400:
            return

        error_code = body.get("error", {}).get("code", 0)

        logger.warning(
            "meta.api.error",
            path=path,
            http_status=status_code,
            error_code=error_code,
            elapsed_ms=elapsed_ms,
            body=body,
        )

        if status_code == 429 or error_code == 130429:
            raise MetaRateLimitError(status_code, body)

        error_type = body.get("error", {}).get("type", "")
        # Genuine auth/permission errors: bad token (190), permissions denied (200, 10, 3), or HTTP 401/403.
        # OAuthException code 100 = "Invalid parameter" — a validation error, NOT an auth error.
        # Treating code 100 as auth would show misleading "PERMISSION_ERROR" for bad template data.
        _AUTH_ERROR_CODES = {190, 200, 10, 3}
        if status_code in (401, 403) or error_code in _AUTH_ERROR_CODES:
            raise MetaAuthError(status_code, body)
        if error_type == "OAuthException" and error_code not in {100}:
            raise MetaAuthError(status_code, body)

        if status_code >= 500:
            raise MetaTransientError(status_code, body)

        # 4xx that are not auth/rate — caller bug (bad phone ID, bad template, etc.)
        raise MetaAPIError(status_code, body)

    # ── Rate limit helper ──────────────────────────────────────────────────────

    async def _check_rate_limit(self, phone_number_id: str) -> None:
        """Enforce 80 msg/s local rate limit before hitting Meta."""
        if self._rate_limiter is None:
            return
        allowed = await self._rate_limiter.acquire(phone_number_id)
        if not allowed:
            raise MetaRateLimitError(
                429,
                {"error": {"code": 130429, "message": "Local rate limit: 80 msg/s exceeded"}},
            )

    # ── Send messages ──────────────────────────────────────────────────────────

    async def send_text(
        self,
        phone_number_id: str,
        to: str,
        body: str,
        preview_url: bool = False,
    ) -> SendResult:
        """Send a plain text message.

        Args:
            phone_number_id: Meta's phone number ID (NOT the display number)
            to: Recipient E.164 without '+', e.g. "919876543210"
            body: Message text (max 4096 chars)
            preview_url: Show link preview if URL detected
        """
        await self._check_rate_limit(phone_number_id)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body},
        }
        logger.info("meta.send_text", phone_number_id=phone_number_id, to=to)
        resp = await self._post(f"{phone_number_id}/messages", payload)
        return self._extract_send_result(resp, to)

    async def send_template(
        self,
        phone_number_id: str,
        to: str,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
    ) -> SendResult:
        """Send an approved message template.

        Args:
            phone_number_id: Meta's phone number ID
            to: Recipient E.164 without '+'
            template_name: Exact template name as approved by Meta
            language_code: e.g. "en_US", "en", "hi"
            components: Template parameter components per Meta spec:
                [
                  {"type": "header", "parameters": [{"type": "text", "text": "Hello"}]},
                  {"type": "body", "parameters": [{"type": "text", "text": "{{1}} value"}]},
                  {"type": "button", "sub_type": "quick_reply", "index": "0",
                   "parameters": [{"type": "payload", "payload": "YES"}]}
                ]
        """
        await self._check_rate_limit(phone_number_id)

        template_payload: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            template_payload["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": template_payload,
        }
        logger.info(
            "meta.send_template",
            phone_number_id=phone_number_id,
            to=to,
            template=template_name,
            language=language_code,
        )
        resp = await self._post(f"{phone_number_id}/messages", payload)
        return self._extract_send_result(resp, to)

    async def send_image(
        self,
        phone_number_id: str,
        to: str,
        image_url: str | None = None,
        image_id: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        """Send an image via uploaded media_id (preferred) or public URL."""
        if not image_url and not image_id:
            raise ValueError("Either image_url or image_id must be provided")
        await self._check_rate_limit(phone_number_id)
        media_obj: dict[str, Any] = {"id": image_id} if image_id else {"link": image_url}
        if caption:
            media_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": media_obj,
        }
        resp = await self._post(f"{phone_number_id}/messages", payload)
        return self._extract_send_result(resp, to)

    async def send_document(
        self,
        phone_number_id: str,
        to: str,
        document_url: str | None = None,
        document_id: str | None = None,
        filename: str = "document",
        caption: str | None = None,
    ) -> SendResult:
        """Send a document via uploaded media_id (preferred) or public URL."""
        if not document_url and not document_id:
            raise ValueError("Either document_url or document_id must be provided")
        await self._check_rate_limit(phone_number_id)
        media_obj: dict[str, Any] = {"id": document_id, "filename": filename} if document_id else {"link": document_url, "filename": filename}
        if caption:
            media_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": media_obj,
        }
        resp = await self._post(f"{phone_number_id}/messages", payload)
        return self._extract_send_result(resp, to)

    async def send_audio(
        self,
        phone_number_id: str,
        to: str,
        audio_url: str | None = None,
        audio_id: str | None = None,
    ) -> SendResult:
        """Send an audio file via uploaded media_id (preferred) or public URL."""
        if not audio_url and not audio_id:
            raise ValueError("Either audio_url or audio_id must be provided")
        await self._check_rate_limit(phone_number_id)
        audio_obj: dict[str, Any] = {"id": audio_id} if audio_id else {"link": audio_url}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "audio",
            "audio": audio_obj,
        }
        resp = await self._post(f"{phone_number_id}/messages", payload)
        return self._extract_send_result(resp, to)

    async def send_video(
        self,
        phone_number_id: str,
        to: str,
        video_url: str | None = None,
        video_id: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        """Send a video via uploaded media_id (preferred) or public URL."""
        if not video_url and not video_id:
            raise ValueError("Either video_url or video_id must be provided")
        await self._check_rate_limit(phone_number_id)
        media_obj: dict[str, Any] = {"id": video_id} if video_id else {"link": video_url}
        if caption:
            media_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "video",
            "video": media_obj,
        }
        resp = await self._post(f"{phone_number_id}/messages", payload)
        return self._extract_send_result(resp, to)

    async def send_location(
        self,
        phone_number_id: str,
        to: str,
        latitude: float,
        longitude: float,
        name: str | None = None,
        address: str | None = None,
    ) -> SendResult:
        """Send a location pin."""
        await self._check_rate_limit(phone_number_id)
        location_obj: dict[str, Any] = {
            "latitude": str(latitude),
            "longitude": str(longitude),
        }
        if name:
            location_obj["name"] = name
        if address:
            location_obj["address"] = address
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "location",
            "location": location_obj,
        }
        resp = await self._post(f"{phone_number_id}/messages", payload)
        return self._extract_send_result(resp, to)

    async def mark_read(self, phone_number_id: str, wa_message_id: str) -> dict:
        """Mark an inbound message as read (shows blue ticks to sender)."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wa_message_id,
        }
        return await self._post(f"{phone_number_id}/messages", payload)

    # ── WABA / phone number management ────────────────────────────────────────

    async def get_phone_numbers(self, waba_id: str) -> list[dict]:
        """List all phone numbers registered to a WABA.

        Returns Meta's phone_numbers array with fields:
          id, display_phone_number, verified_name, quality_rating,
          code_verification_status, messaging_limit_tier
        """
        data = await self._get(f"{waba_id}/phone_numbers")
        return data.get("data", [])

    async def get_phone_number(self, phone_number_id: str) -> dict:
        """Get details for a single phone number."""
        return await self._get(
            phone_number_id,
            params={"fields": "id,display_phone_number,verified_name,quality_rating,messaging_limit_tier"},
        )

    # ── Template management ────────────────────────────────────────────────────

    async def get_templates(self, waba_id: str, limit: int = 100) -> list[dict]:
        """List all message templates for a WABA.

        Returns Meta's message_templates array with status, components, etc.
        """
        data = await self._get(
            f"{waba_id}/message_templates",
            params={"limit": limit},
        )
        return data.get("data", [])

    async def get_template(self, waba_id: str, template_name: str) -> dict | None:
        """Get a single template by name. Returns None if not found."""
        templates = await self.get_templates(waba_id)
        return next((t for t in templates if t.get("name") == template_name), None)

    async def submit_template(
        self,
        waba_id: str,
        name: str,
        category: str,
        language: str,
        components: list[dict],
    ) -> dict:
        """Submit a new template to Meta for approval.

        Args:
            waba_id: Meta WABA ID
            name: Template name (lowercase, underscores, no spaces)
            category: MARKETING | UTILITY | AUTHENTICATION
            language: e.g. "en_US", "hi", "en"
            components: Full Meta template component structure

        Returns:
            Meta response: {"id": "...", "status": "PENDING", "category": "..."}
        """
        payload = {
            "name": name,
            "category": category,
            "language": language,
            "components": components,
        }
        return await self._post(f"{waba_id}/message_templates", payload)

    async def update_template(self, template_id: str, components: list[dict]) -> dict:
        """Update the components of an existing template.

        Args:
            template_id: Meta's template ID (the numeric string from submit_template)
            components: New component structure

        Returns:
            {"success": true} on success
        """
        return await self._post(template_id, {"components": components})

    async def delete_template(self, waba_id: str, template_name: str, template_id: str | None = None) -> dict:
        """Delete a message template from Meta.

        Deletes ALL language variants with the given name.
        If template_id is provided it is sent as hsm_id to target a specific variant.

        Args:
            waba_id: Meta WABA ID
            template_name: Template name (as submitted)
            template_id: Optional Meta template ID to narrow deletion to one variant

        Returns:
            {"success": true} on success
        """
        params: dict = {"name": template_name}
        if template_id:
            params["hsm_id"] = template_id
        return await self._delete(f"{waba_id}/message_templates", params=params)

    # ── Media ──────────────────────────────────────────────────────────────────

    async def upload_media(
        self,
        phone_number_id: str,
        file_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> str:
        """Upload a media file to Meta and return the media_id.

        Use the returned media_id in send_image / send_document / send_audio / send_video.
        Uploaded media is available for 30 days on Meta's servers.
        """
        url = f"{META_BASE_URL}/{phone_number_id}/media"
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    data={"messaging_product": "whatsapp", "type": mime_type},
                    files={"file": (filename, file_bytes, mime_type)},
                )
        except httpx.ConnectError as exc:
            raise MetaAPIError(0, {"error": {"message": f"Cannot reach Meta API: {exc}"}}) from exc
        except httpx.TimeoutException as exc:
            raise MetaAPIError(0, {"error": {"message": f"Meta API timed out: {exc}"}}) from exc

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        body = self._parse_body(resp)
        self._raise_for_error(resp.status_code, body, f"{phone_number_id}/media", elapsed_ms)

        media_id = body.get("id")
        if not media_id:
            raise MetaAPIError(0, {"error": {"message": "Meta did not return media_id after upload"}})

        logger.info("meta.media_uploaded", phone_number_id=phone_number_id, media_id=media_id, elapsed_ms=elapsed_ms)
        return str(media_id)

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Download media bytes from Meta. Returns (content_bytes, mime_type).

        Fetches a fresh temporary URL first (they expire in 5 min), then downloads.
        """
        meta_info = await self._get(media_id)
        download_url = meta_info.get("url", "")
        mime_type = meta_info.get("mime_type", "application/octet-stream")
        if not download_url:
            raise MetaAPIError(0, {"error": {"message": "No download URL in Meta media response"}})

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(
                    download_url,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.ConnectError as exc:
            raise MetaAPIError(0, {"error": {"message": f"Cannot reach Meta media server: {exc}"}}) from exc

        if resp.status_code >= 400:
            raise MetaAPIError(resp.status_code, {"error": {"message": f"Media download failed: HTTP {resp.status_code}"}})

        return resp.content, mime_type

    async def get_media_url(self, media_id: str) -> str:
        """Get the temporary download URL for a media object.

        Media URLs expire after 5 minutes — download immediately.
        """
        data = await self._get(media_id)
        return data.get("url", "")

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_send_result(resp: dict, to: str) -> SendResult:
        """Extract wamid from Meta's send response."""
        messages = resp.get("messages", [])
        if not messages:
            # Unexpected — return unknown id
            return SendResult(
                wa_message_id="unknown",
                recipient_phone=to,
                status="unknown",
                raw=resp,
            )
        return SendResult(
            wa_message_id=messages[0].get("id", ""),
            recipient_phone=to,
            status=messages[0].get("message_status", "accepted"),
            raw=resp,
        )

"""Meta WABA Provisioning API — Embedded Signup + Business Management.

This module handles the full lifecycle of connecting a client's WhatsApp
Business Account to TierceMsg:

  Step 1 — Embedded Signup (frontend):
    Client clicks "Connect WhatsApp" → Meta popup → client authorizes
    → Meta returns a short-lived `code` to your frontend

  Step 2 — Exchange code (this module):
    POST /waba/connect/embedded-signup {code: "..."}
    → exchange_code_for_token(code) → user_access_token
    → get_wabas_for_token(user_access_token) → list of WABAs
    → subscribe_app_to_waba(waba_id, user_access_token)
    → Save WABA + phone numbers to DB

  Step 3 — Register phone number (if needed):
    POST /waba/phone-numbers/{id}/register  {pin: "123456"}
    → register_phone_number(phone_number_id, pin)

  Step 4 — Verify phone number (OTP):
    POST /waba/phone-numbers/{id}/request-code  {method: "SMS"}
    POST /waba/phone-numbers/{id}/verify-code   {code: "123456"}

Meta API references:
  https://developers.facebook.com/docs/whatsapp/embedded-signup
  https://developers.facebook.com/docs/whatsapp/business-management-api
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from app.integration.meta.exceptions import MetaAPIError, MetaAuthError, MetaTransientError
from app.core.config import settings

META_API_VERSION = "v25.0"
META_BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"
REQUEST_TIMEOUT = 15.0


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class WABAInfo:
    """WABA details returned from Meta."""
    waba_id: str
    name: str
    currency: str
    timezone_id: str
    phone_numbers: list[PhoneNumberInfo] = field(default_factory=list)
    # Extended Meta fields
    message_template_namespace: str | None = None
    account_review_status: str | None = None
    business_id: str | None = None


@dataclass
class PhoneNumberInfo:
    """Phone number details from Meta."""
    phone_number_id: str
    display_number: str         # e.g. "+91 98765 43210"
    verified_name: str          # business name shown on WhatsApp
    quality_rating: str         # GREEN | YELLOW | RED | UNKNOWN
    code_verification_status: str   # VERIFIED | NOT_VERIFIED
    messaging_limit_tier: str   # TIER_1K | TIER_10K | TIER_100K | TIER_UNLIMITED
    # Extended Meta fields
    platform_type: str | None = None        # CLOUD_API | ON_PREMISE
    throughput_level: str | None = None     # STANDARD | HIGH
    account_mode: str | None = None         # SANDBOX | LIVE
    name_status: str | None = None          # APPROVED | PENDING | DECLINED | etc.
    last_onboarded_time: datetime | None = None


@dataclass
class TokenInfo:
    """Result of code exchange."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None    # None = never expires (system user token)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_phone_info(p: dict) -> PhoneNumberInfo:
    """Build a PhoneNumberInfo from a Meta phone number dict."""
    last_onboarded: datetime | None = None
    raw_ts = p.get("last_onboarded_time")
    if raw_ts:
        try:
            last_onboarded = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    throughput = p.get("throughput", {})
    throughput_level = throughput.get("level") if isinstance(throughput, dict) else None

    return PhoneNumberInfo(
        phone_number_id=p["id"],
        display_number=p.get("display_phone_number", ""),
        verified_name=p.get("verified_name", ""),
        quality_rating=p.get("quality_rating", "UNKNOWN"),
        code_verification_status=p.get("code_verification_status", "NOT_VERIFIED"),
        messaging_limit_tier=p.get("messaging_limit_tier", "TIER_1K"),
        platform_type=p.get("platform_type"),
        throughput_level=throughput_level,
        account_mode=p.get("account_mode"),
        name_status=p.get("name_status"),
        last_onboarded_time=last_onboarded,
    )


# ── Provisioning client ───────────────────────────────────────────────────────

class MetaProvisioning:
    """Handles Embedded Signup and WABA provisioning API calls.

    Unlike MetaClient (which is per-org), this class uses your app-level
    credentials (META_APP_ID + META_APP_SECRET) and is instantiated once.
    """

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self._app_id = app_id or settings.META_APP_ID
        self._app_secret = app_secret or settings.META_APP_SECRET

    @property
    def _app_token(self) -> str:
        """App-level access token: app_id|app_secret."""
        return f"{self._app_id}|{self._app_secret}"

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{META_BASE_URL}/{path}"
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.get(url, params=params or {})
        except httpx.ConnectError as exc:
            raise MetaAPIError(0, {"error": {"message": f"Cannot reach Meta API: {exc}"}}) from exc
        except httpx.TimeoutException as exc:
            raise MetaAPIError(0, {"error": {"message": f"Meta API request timed out: {exc}"}}) from exc
        body = self._parse(resp)
        self._raise_for_error(resp.status_code, body)
        return body

    async def _post(self, path: str, payload: dict | None = None, params: dict | None = None) -> dict:
        url = f"{META_BASE_URL}/{path}"
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(url, json=payload or {}, params=params or {})
        except httpx.ConnectError as exc:
            raise MetaAPIError(0, {"error": {"message": f"Cannot reach Meta API: {exc}"}}) from exc
        except httpx.TimeoutException as exc:
            raise MetaAPIError(0, {"error": {"message": f"Meta API request timed out: {exc}"}}) from exc
        body = self._parse(resp)
        self._raise_for_error(resp.status_code, body)
        return body

    @staticmethod
    def _parse(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    @staticmethod
    def _raise_for_error(status_code: int, body: dict) -> None:
        if status_code < 400:
            return
        if status_code in (401, 403):
            raise MetaAuthError(status_code, body)
        if status_code >= 500:
            raise MetaTransientError(status_code, body)
        raise MetaAPIError(status_code, body)

    # ── Step 1: Exchange code for access token ────────────────────────────────

    async def exchange_code_for_token(self, code: str) -> TokenInfo:
        """Exchange the Embedded Signup code for a user access token.

        Meta Embedded Signup gives the frontend a short-lived `code`.
        This method exchanges it for a user access token.

        Args:
            code: The code returned by Meta's JS SDK after Embedded Signup

        Returns:
            TokenInfo with access_token (user token, short-lived ~1hr)
        """
        data = await self._get(
            "oauth/access_token",
            params={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "code": code,
            },
        )
        logger.info("meta.provisioning.code_exchanged")
        return TokenInfo(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            expires_in=data.get("expires_in"),
        )

    # ── Step 2: Get WABAs accessible by this token ────────────────────────────

    async def get_wabas_for_token(self, user_access_token: str) -> list[WABAInfo]:
        """Get all WABAs the user authorized during Embedded Signup.

        Returns a list of WABAInfo objects with phone numbers attached.
        """
        data = await self._get(
            "me/businesses",
            params={
                "fields": "whatsapp_business_accounts{id,name,currency,timezone_id,message_template_namespace,account_review_status,phone_numbers{id,display_phone_number,verified_name,quality_rating,code_verification_status,messaging_limit_tier,platform_type,throughput,account_mode,name_status,last_onboarded_time}}",
                "access_token": user_access_token,
            },
        )

        wabas = []
        for business in data.get("data", []):
            for waba_raw in business.get("whatsapp_business_accounts", {}).get("data", []):
                phones = [
                    _parse_phone_info(p)
                    for p in waba_raw.get("phone_numbers", {}).get("data", [])
                ]
                wabas.append(WABAInfo(
                    waba_id=waba_raw["id"],
                    name=waba_raw.get("name", ""),
                    currency=waba_raw.get("currency", "USD"),
                    timezone_id=waba_raw.get("timezone_id", "1"),
                    phone_numbers=phones,
                    message_template_namespace=waba_raw.get("message_template_namespace"),
                    account_review_status=waba_raw.get("account_review_status"),
                    business_id=business.get("id"),
                ))

        logger.info("meta.provisioning.wabas_fetched", count=len(wabas))
        return wabas

    async def get_waba_details(self, waba_id: str, access_token: str) -> dict:
        """Get details of a specific WABA."""
        return await self._get(
            waba_id,
            params={
                "fields": "id,name,currency,timezone_id,message_template_namespace,account_review_status",
                "access_token": access_token,
            },
        )

    async def get_phone_numbers(self, waba_id: str, access_token: str) -> list[PhoneNumberInfo]:
        """List all phone numbers registered to a WABA."""
        data = await self._get(
            f"{waba_id}/phone_numbers",
            params={
                "fields": "id,display_phone_number,verified_name,quality_rating,code_verification_status,messaging_limit_tier,platform_type,throughput,account_mode,name_status,last_onboarded_time",
                "access_token": access_token,
            },
        )
        return [_parse_phone_info(p) for p in data.get("data", [])]

    async def get_phone_number_details(self, phone_number_id: str, access_token: str) -> PhoneNumberInfo:
        """Fetch details for a single phone number by its Meta ID."""
        data = await self._get(
            phone_number_id,
            params={
                "fields": "id,display_phone_number,verified_name,quality_rating,code_verification_status,messaging_limit_tier,platform_type,throughput,account_mode,name_status,last_onboarded_time",
                "access_token": access_token,
            },
        )
        return _parse_phone_info(data)

    # ── WABA creation ─────────────────────────────────────────────────────────

    async def create_waba(
        self,
        business_id: str,
        name: str,
        currency: str,
        timezone_id: str,
        access_token: str,
    ) -> dict:
        """Create a new WhatsApp Business Account under a Meta Business.

        Requires a token with the `business_management` permission granted for
        the target business (typically a system user token or partner token).

        Args:
            business_id: Meta Business Account ID (parent)
            name: Display name for the new WABA
            currency: ISO 4217 currency code, e.g. "USD", "INR"
            timezone_id: Meta timezone ID string, e.g. "1" (UTC), "Asia/Kolkata"
            access_token: Token with business_management permission

        Returns:
            Raw Meta response dict (contains "id" of new WABA)
        """
        data = await self._post(
            f"{business_id}/whatsapp_business_accounts",
            payload={
                "name": name,
                "currency": currency,
                "timezone_id": timezone_id,
            },
            params={"access_token": access_token},
        )
        logger.info(
            "meta.provisioning.waba_created",
            business_id=business_id,
            name=name,
            new_waba_id=data.get("id"),
        )
        return data

    # ── Step 3: Subscribe app to WABA webhooks ────────────────────────────────

    async def subscribe_app_to_waba(self, waba_id: str, access_token: str) -> bool:
        """Subscribe your Meta App to receive webhooks for this WABA.

        Must be called once after onboarding a new WABA.
        After this, Meta will send webhooks (messages, status updates) to your
        configured webhook URL for this WABA.

        Args:
            waba_id: Meta WABA ID
            access_token: User or system user access token with
                          whatsapp_business_management permission

        Returns:
            True if subscribed successfully
        """
        data = await self._post(
            f"{waba_id}/subscribed_apps",
            params={"access_token": access_token},
        )
        success = data.get("success", False)
        logger.info(
            "meta.provisioning.webhook_subscribed",
            waba_id=waba_id,
            success=success,
        )
        return success

    async def get_subscribed_apps(self, waba_id: str, access_token: str) -> list[dict]:
        """Get apps currently subscribed to this WABA's webhooks."""
        data = await self._get(
            f"{waba_id}/subscribed_apps",
            params={"access_token": access_token},
        )
        return data.get("data", [])

    # ── Step 4: Register phone number with Cloud API ──────────────────────────

    async def register_phone_number(
        self,
        phone_number_id: str,
        pin: str,
        access_token: str,
    ) -> bool:
        """Register a phone number to use the WhatsApp Cloud API.

        Required for new phone numbers before they can send messages.
        The PIN is a 6-digit code you set — store it safely, needed for re-registration.

        Args:
            phone_number_id: Meta's phone number ID
            pin: 6-digit PIN you choose (required for future re-registration)
            access_token: Token with whatsapp_business_messaging permission

        Returns:
            True if registered successfully
        """
        data = await self._post(
            f"{phone_number_id}/register",
            payload={
                "messaging_product": "whatsapp",
                "pin": pin,
            },
            params={"access_token": access_token},
        )
        success = data.get("success", False)
        logger.info(
            "meta.provisioning.phone_registered",
            phone_number_id=phone_number_id,
            success=success,
        )
        return success

    async def deregister_phone_number(
        self,
        phone_number_id: str,
        access_token: str,
    ) -> bool:
        """Deregister a phone number from the WhatsApp Cloud API.

        Stops the number from sending/receiving messages via Cloud API.
        The number can be re-registered later with register_phone_number.

        Args:
            phone_number_id: Meta's phone number ID
            access_token: Token with whatsapp_business_messaging permission

        Returns:
            True if deregistered successfully
        """
        data = await self._post(
            f"{phone_number_id}/deregister",
            params={"access_token": access_token},
        )
        success = data.get("success", False)
        logger.info(
            "meta.provisioning.phone_deregistered",
            phone_number_id=phone_number_id,
            success=success,
        )
        return success

    # ── Step 5: Verify phone number (OTP) ────────────────────────────────────

    async def request_verification_code(
        self,
        phone_number_id: str,
        code_method: str,
        language: str,
        access_token: str,
    ) -> bool:
        """Request an OTP to verify a phone number.

        Args:
            phone_number_id: Meta's phone number ID
            code_method: "SMS" or "VOICE"
            language: e.g. "en_US", "hi_IN"
            access_token: Token with whatsapp_business_messaging permission

        Returns:
            True if OTP was sent
        """
        data = await self._post(
            f"{phone_number_id}/request_code",
            payload={
                "code_method": code_method,
                "language": language,
            },
            params={"access_token": access_token},
        )
        success = data.get("success", False)
        logger.info(
            "meta.provisioning.verification_code_requested",
            phone_number_id=phone_number_id,
            method=code_method,
        )
        return success

    async def verify_phone_number(
        self,
        phone_number_id: str,
        code: str,
        access_token: str,
    ) -> bool:
        """Verify a phone number with the OTP received.

        Args:
            phone_number_id: Meta's phone number ID
            code: The OTP received via SMS/VOICE
            access_token: Token with whatsapp_business_messaging permission

        Returns:
            True if verified successfully
        """
        data = await self._post(
            f"{phone_number_id}/verify_code",
            payload={"code": code},
            params={"access_token": access_token},
        )
        success = data.get("success", False)
        logger.info(
            "meta.provisioning.phone_verified",
            phone_number_id=phone_number_id,
            success=success,
        )
        return success

    # ── Debug token ───────────────────────────────────────────────────────────

    async def debug_token(self, input_token: str) -> dict:
        """Inspect a token — useful for checking scopes and expiry."""
        return await self._get(
            "debug_token",
            params={
                "input_token": input_token,
                "access_token": self._app_token,
            },
        )


# ── Singleton factory ─────────────────────────────────────────────────────────

def get_provisioning_client() -> MetaProvisioning:
    """Return a MetaProvisioning instance using app-level credentials from settings."""
    return MetaProvisioning(
        app_id=settings.META_APP_ID,
        app_secret=settings.META_APP_SECRET,
    )

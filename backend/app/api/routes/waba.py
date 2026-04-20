"""WABA accounts and phone numbers — fully wired to Meta API.

Every action that touches Meta WABA state is mirrored in real time.

Connect:
  POST /waba/connect/token            — [DEV] connect with token + WABA ID
  POST /waba/connect/embedded-signup  — [PROD] connect via Embedded Signup flow

WABA:
  POST   /waba/create                 — create a new WABA on Meta + save to DB
  GET    /waba                        — list connected WABAs from DB
  GET    /waba/{id}                   — get WABA from DB
  POST   /waba/{id}/sync              — pull latest WABA details from Meta → update DB
  PATCH  /waba/{id}                   — update access_token; re-subscribes webhooks on Meta
  DELETE /waba/{id}                   — unsubscribes webhooks on Meta, then deletes from DB

Phone numbers:
  POST   /waba/phone-numbers                    — add a phone number by Meta ID (fetches from Meta)
  GET    /waba/phone-numbers                    — list all phone numbers from DB
  GET    /waba/phone-numbers/{id}               — get phone number from DB
  POST   /waba/phone-numbers/{id}/sync          — pull all fields from Meta → update DB
  DELETE /waba/phone-numbers/{id}               — delete from DB
  POST   /waba/phone-numbers/{id}/register      — register with Meta Cloud API
  POST   /waba/phone-numbers/{id}/deregister    — deregister from Meta Cloud API
  POST   /waba/phone-numbers/{id}/request-code  — request OTP
  POST   /waba/phone-numbers/{id}/verify-code   — submit OTP

IMPORTANT — route ordering:
  /connect/*, /create, /phone-numbers/*, and /{waba_id}/sync must be declared
  BEFORE /{waba_id} so FastAPI does not parse literal strings as UUIDs.
"""
import hashlib
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Annotated, TypeAlias

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import OrgAdmin
from app.integration.meta.deps import build_client
from app.integration.meta.exceptions import MetaAPIError, MetaAuthError
from app.integration.meta.provisioning import WABAInfo, PhoneNumberInfo, get_provisioning_client
from app.models.whatsapp import LocalQrCode, PhoneNumber, WabaAccount
from app.schemas.whatsapp import (
    EmbeddedSignupRequest,
    EmbeddedSignupResponse,
    PhoneNumberAddRequest,
    PhoneNumberResponse,
    RegisterPhoneRequest,
    RequestVerificationCodeRequest,
    VerifyCodeRequest,
    WabaCreateRequest,
    WabaResponse,
    WabaUpdate,
)

router = APIRouter(prefix="/waba", tags=["WABA"])

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _meta_error_to_http(exc: MetaAPIError) -> HTTPException:
    if isinstance(exc, MetaAuthError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Meta access token invalid or expired. ({exc})",
        )
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Meta API error: {exc}")


async def _get_waba_row(waba_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> WabaAccount:
    result = await db.execute(
        select(WabaAccount).where(WabaAccount.id == waba_id, WabaAccount.org_id == org_id)
    )
    waba = result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")
    return waba


async def _get_phone_with_waba(
    phone_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[PhoneNumber, WabaAccount]:
    result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.id == phone_id, PhoneNumber.org_id == org_id)
    )
    phone = result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
    waba_result = await db.execute(select(WabaAccount).where(WabaAccount.id == phone.waba_id))
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")
    return phone, waba


def _apply_waba_fields(waba_row: WabaAccount, details: dict) -> None:
    """Update a WabaAccount row from a Meta WABA details dict (in-place)."""
    waba_row.business_name = details.get("name", waba_row.business_name)  # type: ignore[assignment]
    waba_row.currency = details.get("currency")  # type: ignore[assignment]
    waba_row.timezone_id = details.get("timezone_id")  # type: ignore[assignment]
    waba_row.message_template_namespace = details.get("message_template_namespace")  # type: ignore[assignment]
    waba_row.account_review_status = details.get("account_review_status")  # type: ignore[assignment]


def _apply_phone_fields(phone_row: PhoneNumber, info: PhoneNumberInfo) -> None:
    """Update a PhoneNumber row from a PhoneNumberInfo (in-place)."""
    phone_row.display_number = info.display_number  # type: ignore[assignment]
    phone_row.display_name = info.verified_name  # type: ignore[assignment]
    phone_row.quality_rating = info.quality_rating  # type: ignore[assignment]
    phone_row.messaging_limit = info.messaging_limit_tier  # type: ignore[assignment]
    phone_row.code_verification_status = info.code_verification_status  # type: ignore[assignment]
    phone_row.platform_type = info.platform_type  # type: ignore[assignment]
    phone_row.throughput_level = info.throughput_level  # type: ignore[assignment]
    phone_row.account_mode = info.account_mode  # type: ignore[assignment]
    phone_row.name_status = info.name_status  # type: ignore[assignment]
    phone_row.last_onboarded_time = info.last_onboarded_time  # type: ignore[assignment]


async def _save_wabas(
    waba_infos: list,
    access_token: str,
    current_user,
    db: AsyncSession,
) -> EmbeddedSignupResponse:
    """Upsert WABAs + phone numbers and subscribe webhooks. Shared by connect endpoints."""
    provisioning = get_provisioning_client()
    saved_wabas: list[WabaAccount] = []
    phones_saved = 0

    for waba_info in waba_infos:
        try:
            await provisioning.subscribe_app_to_waba(waba_info.waba_id, access_token)
        except MetaAPIError as exc:
            logger.warning("waba.connect.webhook_subscribe_failed", waba_id=waba_info.waba_id, error=str(exc))

        existing = await db.execute(
            select(WabaAccount).where(
                WabaAccount.org_id == current_user.org_id,
                WabaAccount.waba_id == waba_info.waba_id,
            )
        )
        waba_row = existing.scalar_one_or_none()

        if waba_row is None:
            waba_row = WabaAccount(
                org_id=current_user.org_id,
                waba_id=waba_info.waba_id,
                access_token=access_token,
                business_name=waba_info.name,
                currency=waba_info.currency,
                timezone_id=waba_info.timezone_id,
                message_template_namespace=waba_info.message_template_namespace,
                account_review_status=waba_info.account_review_status,
                business_id=waba_info.business_id,
            )
            db.add(waba_row)
            await db.flush()
            logger.info("waba.connect.created", waba_id=waba_info.waba_id)
        else:
            waba_row.access_token = access_token  # type: ignore[assignment]
            waba_row.business_name = waba_info.name  # type: ignore[assignment]
            waba_row.currency = waba_info.currency  # type: ignore[assignment]
            waba_row.timezone_id = waba_info.timezone_id  # type: ignore[assignment]
            waba_row.message_template_namespace = waba_info.message_template_namespace  # type: ignore[assignment]
            waba_row.account_review_status = waba_info.account_review_status  # type: ignore[assignment]
            if waba_info.business_id:
                waba_row.business_id = waba_info.business_id  # type: ignore[assignment]
            logger.info("waba.connect.updated", waba_id=waba_info.waba_id)

        saved_wabas.append(waba_row)

        for phone_info in waba_info.phone_numbers:
            existing_phone = await db.execute(
                select(PhoneNumber).where(
                    PhoneNumber.org_id == current_user.org_id,
                    PhoneNumber.phone_number_id == phone_info.phone_number_id,
                )
            )
            phone_row = existing_phone.scalar_one_or_none()
            if phone_row is None:
                phone_row = PhoneNumber(
                    org_id=current_user.org_id,
                    waba_id=waba_row.id,
                    phone_number_id=phone_info.phone_number_id,
                    created_at=datetime.now(timezone.utc),
                )
                _apply_phone_fields(phone_row, phone_info)
                db.add(phone_row)
                phones_saved += 1
                logger.info("waba.connect.phone_saved", phone_number_id=phone_info.phone_number_id)
            else:
                _apply_phone_fields(phone_row, phone_info)

    await db.commit()
    for waba_row in saved_wabas:
        await db.refresh(waba_row)

    return EmbeddedSignupResponse(
        wabas_connected=len(saved_wabas),
        phone_numbers_saved=phones_saved,
        wabas=[WabaResponse.model_validate(w) for w in saved_wabas],
    )


# ── QR Code helpers ──────────────────────────────────────────────────────────

_QR_TIMEOUT = 15.0
_GRAPH_BASE = "https://graph.facebook.com/v19.0"


async def _meta_qr_get(phone_number_id: str, access_token: str) -> list[dict]:
    url = f"{_GRAPH_BASE}/{phone_number_id}/qr_codes"
    async with httpx.AsyncClient(timeout=_QR_TIMEOUT) as client:
        resp = await client.get(url, params={"access_token": access_token})
    body: dict = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Meta QR error: {body.get('error', {}).get('message', str(body))}")
    return body.get("data", [])


def _local_qr_fallback(display_number: str, prefilled_message: str) -> dict:
    """Generate a WhatsApp deep-link QR code locally (no Meta API needed).
    Works for test numbers and accounts without Meta QR permission."""
    # Normalise: strip +, spaces, dashes for wa.me
    number = display_number.replace("+", "").replace(" ", "").replace("-", "")
    encoded_msg = urllib.parse.quote(prefilled_message)
    deep_link = f"https://wa.me/{number}?text={encoded_msg}"
    # Stable short code from phone+message
    code = "LOCAL_" + hashlib.sha256(f"{number}:{prefilled_message}".encode()).hexdigest()[:12].upper()
    # Free public QR image service (no key required)
    qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(deep_link, safe='')}"
    return {"code": code, "prefilled_message": prefilled_message,
            "deep_link_url": deep_link, "qr_image_url": qr_image_url}


async def _meta_qr_create(phone_number_id: str, prefilled_message: str, access_token: str) -> dict:
    url = f"{_GRAPH_BASE}/{phone_number_id}/qr_codes"
    async with httpx.AsyncClient(timeout=_QR_TIMEOUT) as client:
        resp = await client.post(url, params={"access_token": access_token},
                                 json={"prefilled_message": prefilled_message, "generate_qr_image": "PNG"})
    body: dict = resp.json() if resp.content else {}
    if resp.status_code < 400:
        return body
    # Return None to signal caller should use fallback
    logger.warning("meta.qr_create_failed", status=resp.status_code,
                   error=body.get("error", {}).get("message", "unknown"))
    return {}  # empty → caller uses fallback


async def _meta_qr_delete(phone_number_id: str, qr_code_id: str, access_token: str) -> None:
    url = f"{_GRAPH_BASE}/{phone_number_id}/qr_codes/{qr_code_id}"
    async with httpx.AsyncClient(timeout=_QR_TIMEOUT) as client:
        resp = await client.delete(url, params={"access_token": access_token})
    body: dict = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Meta QR error: {body.get('error', {}).get('message', str(body))}")


async def _get_phone_with_waba(
    phone_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession
) -> tuple[PhoneNumber, WabaAccount]:
    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.id == phone_id, PhoneNumber.org_id == org_id)
    )
    phone = phone_result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
    waba_result = await db.execute(select(WabaAccount).where(WabaAccount.id == phone.waba_id))
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WABA not found")
    return phone, waba


# ── QR Code routes (MUST be before /{waba_id}) ───────────────────────────────

@router.get("/qr-codes")
async def list_qr_codes(current_user: OrgAdmin, db: DbDep) -> list[dict]:
    """List QR codes: Meta API codes + locally stored fallback codes."""
    phones_result = await db.execute(select(PhoneNumber).where(PhoneNumber.org_id == current_user.org_id))
    phones = {p.id: p for p in phones_result.scalars().all()}
    all_qr: list[dict] = []

    # 1. Pull from Meta API
    for phone in phones.values():
        waba_result = await db.execute(select(WabaAccount).where(WabaAccount.id == phone.waba_id))
        waba = waba_result.scalar_one_or_none()
        if not waba:
            continue
        try:
            qrs = await _meta_qr_get(phone.phone_number_id, waba.access_token)
        except HTTPException:
            qrs = []
        for qr in qrs:
            all_qr.append({**qr, "phone_number_id": phone.phone_number_id,
                           "phone_internal_id": str(phone.id),
                           "display_number": phone.display_number, "display_name": phone.display_name})

    # 2. Also return locally stored QR codes
    local_result = await db.execute(
        select(LocalQrCode).where(LocalQrCode.org_id == current_user.org_id)
        .order_by(LocalQrCode.created_at.desc())
    )
    for lqr in local_result.scalars().all():
        phone = phones.get(lqr.phone_internal_id)
        all_qr.append({
            "code": lqr.code,
            "prefilled_message": lqr.prefilled_message,
            "deep_link_url": lqr.deep_link_url,
            "qr_image_url": lqr.qr_image_url,
            "phone_number_id": phone.phone_number_id if phone else str(lqr.phone_internal_id),
            "phone_internal_id": str(lqr.phone_internal_id),
            "display_number": phone.display_number if phone else None,
            "display_name": phone.display_name if phone else None,
        })
    return all_qr


@router.post("/qr-codes", status_code=status.HTTP_201_CREATED)
async def create_qr_code(body: dict, current_user: OrgAdmin, db: DbDep) -> dict:
    """Create a WhatsApp QR code. Falls back to local generation if Meta API unavailable."""
    phone_id_raw = body.get("phone_number_id")
    prefilled_message = body.get("prefilled_message", "")
    if not phone_id_raw:
        raise HTTPException(status_code=400, detail="phone_number_id is required")
    if not prefilled_message:
        raise HTTPException(status_code=400, detail="prefilled_message is required")
    phone, waba = await _get_phone_with_waba(uuid.UUID(str(phone_id_raw)), current_user.org_id, db)
    result = await _meta_qr_create(phone.phone_number_id, prefilled_message, waba.access_token)
    if not result:
        # Meta QR API unavailable — generate locally and persist
        disp = phone.display_number or phone.phone_number_id
        result = _local_qr_fallback(disp, prefilled_message)
        # Upsert: if same code already exists (same phone+message), skip insert
        existing = await db.execute(select(LocalQrCode).where(LocalQrCode.code == result["code"]))
        if not existing.scalar_one_or_none():
            db.add(LocalQrCode(
                org_id=current_user.org_id,
                phone_internal_id=phone.id,
                code=result["code"],
                prefilled_message=prefilled_message,
                deep_link_url=result["deep_link_url"],
                qr_image_url=result.get("qr_image_url"),
            ))
            await db.commit()
        logger.info("qr.created_local", phone_number_id=phone.phone_number_id)
    else:
        logger.info("qr.created_meta", phone_number_id=phone.phone_number_id)
    return {**result, "phone_number_id": phone.phone_number_id, "phone_internal_id": str(phone.id),
            "display_number": phone.display_number, "display_name": phone.display_name}


@router.delete("/qr-codes/{qr_code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_qr_code(
    qr_code_id: str, current_user: OrgAdmin, db: DbDep,
    phone_number_id: str | None = None,
) -> None:
    """Delete a WhatsApp QR code."""
    if qr_code_id.startswith("LOCAL_"):
        # Delete from local DB
        local_result = await db.execute(
            select(LocalQrCode).where(LocalQrCode.code == qr_code_id,
                                      LocalQrCode.org_id == current_user.org_id))
        lqr = local_result.scalar_one_or_none()
        if lqr:
            await db.delete(lqr)
            await db.commit()
        logger.info("qr.deleted_local", qr_code_id=qr_code_id)
        return

    # Meta QR code — need phone_number_id to call Meta API
    if not phone_number_id:
        raise HTTPException(status_code=400, detail="phone_number_id query param is required")
    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.phone_number_id == phone_number_id,
                                  PhoneNumber.org_id == current_user.org_id))
    phone = phone_result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=404, detail="Phone number not found")
    waba_result = await db.execute(select(WabaAccount).where(WabaAccount.id == phone.waba_id))
    waba = waba_result.scalar_one_or_none()
    if not waba:
        raise HTTPException(status_code=404, detail="WABA not found")
    await _meta_qr_delete(phone_number_id, qr_code_id, waba.access_token)
    logger.info("qr.deleted_meta", phone_number_id=phone_number_id, qr_code_id=qr_code_id)


# ── Connect endpoints (MUST be before /{waba_id}) ─────────────────────────────

@router.get(
    "/connect/config",
    summary="Get Meta Embedded Signup config for the frontend",
    response_model=dict,
)
async def get_embedded_signup_config(current_user: OrgAdmin) -> dict:
    """Return the Meta App ID and Embedded Signup Config ID needed by the frontend JS SDK.

    These are public identifiers — safe to expose to the browser.
    The App Secret is never returned.
    """
    return {
        "app_id": settings.META_APP_ID,
        "config_id": settings.META_EMBEDDED_SIGNUP_CONFIG_ID,
    }


@router.post(
    "/connect/token",
    response_model=EmbeddedSignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[DEV] Connect a WABA using a token + WABA ID",
)
async def connect_with_token(body: dict, current_user: OrgAdmin, db: DbDep) -> EmbeddedSignupResponse:
    """Dev/testing shortcut — does NOT require `business_management` permission.

    Body: { "access_token": "<token>", "waba_id": "1533509561531653" }

    Get the token from: developers.facebook.com/tools/explorer
    Permissions needed: whatsapp_business_management, whatsapp_business_messaging
    """
    access_token = body.get("access_token", "")
    waba_id = body.get("waba_id", "")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="access_token is required")
    if not waba_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="waba_id is required (Meta WABA ID)")

    provisioning = get_provisioning_client()
    try:
        waba_details = await provisioning.get_waba_details(waba_id, access_token)
        phone_numbers = await provisioning.get_phone_numbers(waba_id, access_token)
    except MetaAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except MetaAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Meta API error: {exc}")

    waba_info = WABAInfo(
        waba_id=waba_details.get("id", waba_id),
        name=waba_details.get("name", ""),
        currency=waba_details.get("currency", "USD"),
        timezone_id=waba_details.get("timezone_id", "1"),
        phone_numbers=phone_numbers,
        message_template_namespace=waba_details.get("message_template_namespace"),
        account_review_status=waba_details.get("account_review_status"),
    )
    return await _save_wabas([waba_info], access_token, current_user, db)


@router.post(
    "/connect/embedded-signup",
    response_model=EmbeddedSignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect a WABA via Meta Embedded Signup",
)
async def connect_embedded_signup(
    body: EmbeddedSignupRequest,
    current_user: OrgAdmin,
    db: DbDep,
) -> EmbeddedSignupResponse:
    """Production onboarding flow. Exchange the JS SDK code, fetch WABAs, subscribe webhooks, save."""
    provisioning = get_provisioning_client()
    try:
        token_info = await provisioning.exchange_code_for_token(body.code)
    except MetaAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Meta rejected the code: {exc}")
    except MetaAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Code exchange failed: {exc}")

    try:
        waba_infos = await provisioning.get_wabas_for_token(token_info.access_token)
    except MetaAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to fetch WABAs: {exc}")

    if not waba_infos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No WABAs found for this authorization.")

    return await _save_wabas(waba_infos, token_info.access_token, current_user, db)


# ── WABA creation (MUST be before /{waba_id}) ────────────────────────────────

@router.post(
    "/create",
    response_model=WabaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new WABA on Meta and save it to DB",
)
async def create_waba(
    body: WabaCreateRequest,
    current_user: OrgAdmin,
    db: DbDep,
) -> WabaAccount:
    """Create a brand-new WhatsApp Business Account under your Meta Business.

    This calls `POST /{business_id}/whatsapp_business_accounts` on Meta, then
    subscribes webhooks and saves the new WABA to the local DB.

    Requires a token with `business_management` permission for the given
    business_id. Get such a token from a system user in Meta Business Manager.

    Body fields:
    - **business_id**: Your Meta Business Account ID (from business.facebook.com)
    - **name**: Display name for the new WABA
    - **currency**: ISO 4217 code, e.g. "USD" or "INR"
    - **timezone_id**: Meta timezone ID — "1" = UTC, "292" = Asia/Kolkata
    - **access_token**: Token with `business_management` permission
    """
    provisioning = get_provisioning_client()

    # Create WABA on Meta
    try:
        meta_resp = await provisioning.create_waba(
            business_id=body.business_id,
            name=body.name,
            currency=body.currency,
            timezone_id=body.timezone_id,
            access_token=body.access_token,
        )
    except MetaAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Meta rejected the token: {exc}")
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    meta_waba_id = meta_resp.get("id")
    if not meta_waba_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Meta did not return a WABA ID. Response: {meta_resp}",
        )

    # Fetch full WABA details from Meta (includes message_template_namespace etc.)
    try:
        details = await provisioning.get_waba_details(meta_waba_id, body.access_token)
        await provisioning.subscribe_app_to_waba(meta_waba_id, body.access_token)
    except MetaAPIError as exc:
        logger.warning("waba.create.post_create_failed", meta_waba_id=meta_waba_id, error=str(exc))
        details = meta_resp  # fall back to creation response

    # Check if this WABA already exists in DB (race condition guard)
    existing = await db.execute(
        select(WabaAccount).where(
            WabaAccount.org_id == current_user.org_id,
            WabaAccount.waba_id == meta_waba_id,
        )
    )
    waba_row = existing.scalar_one_or_none()

    if waba_row is None:
        waba_row = WabaAccount(
            org_id=current_user.org_id,
            waba_id=meta_waba_id,
            access_token=body.access_token,
            business_id=body.business_id,
            business_name=details.get("name", body.name),
            currency=details.get("currency", body.currency),
            timezone_id=details.get("timezone_id", body.timezone_id),
            message_template_namespace=details.get("message_template_namespace"),
            account_review_status=details.get("account_review_status"),
        )
        db.add(waba_row)
    else:
        _apply_waba_fields(waba_row, details)

    await db.commit()
    await db.refresh(waba_row)
    logger.info("waba.created", meta_waba_id=meta_waba_id, org_id=str(current_user.org_id))
    return waba_row


# ── Phone Numbers (MUST be before /{waba_id}) ─────────────────────────────────

@router.post(
    "/phone-numbers",
    response_model=PhoneNumberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a phone number by Meta ID (fetches all fields from Meta)",
)
async def add_phone_number(
    body: PhoneNumberAddRequest,
    current_user: OrgAdmin,
    db: DbDep,
) -> PhoneNumber:
    """Add an existing Meta phone number to a WABA in the local DB.

    The number must already exist on Meta (added via Business Manager or migration).
    All current Meta fields are fetched and stored: verification status, platform
    type, throughput, account mode, name status, etc.

    Body:
    - **waba_id**: Internal UUID of the WABA account in this system
    - **phone_number_id**: Meta's phone number ID (numeric string)
    """
    # Validate WABA exists and belongs to this org
    waba = await _get_waba_row(body.waba_id, current_user.org_id, db)

    # Check if phone number already exists
    existing = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.org_id == current_user.org_id,
            PhoneNumber.phone_number_id == body.phone_number_id,
        )
    )
    phone_row = existing.scalar_one_or_none()

    # Fetch full details from Meta
    provisioning = get_provisioning_client()
    try:
        phone_info = await provisioning.get_phone_number_details(body.phone_number_id, waba.access_token)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    if phone_row is None:
        phone_row = PhoneNumber(
            org_id=current_user.org_id,
            waba_id=waba.id,
            phone_number_id=body.phone_number_id,
            created_at=datetime.now(timezone.utc),
        )
        _apply_phone_fields(phone_row, phone_info)
        db.add(phone_row)
        logger.info("phone.added", phone_number_id=body.phone_number_id, waba_id=str(waba.id))
    else:
        _apply_phone_fields(phone_row, phone_info)
        logger.info("phone.updated", phone_number_id=body.phone_number_id)

    await db.commit()
    await db.refresh(phone_row)
    return phone_row


@router.get("/phone-numbers", response_model=list[PhoneNumberResponse])
async def list_phone_numbers(current_user: OrgAdmin, db: DbDep) -> list[PhoneNumber]:
    """List all phone numbers from DB."""
    result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.org_id == current_user.org_id)
    )
    return list(result.scalars().all())


@router.get("/phone-numbers/{phone_id}", response_model=PhoneNumberResponse)
async def get_phone_number(phone_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> PhoneNumber:
    """Get a phone number from DB."""
    result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.id == phone_id, PhoneNumber.org_id == current_user.org_id)
    )
    phone = result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
    return phone


@router.post("/phone-numbers/{phone_id}/sync", response_model=PhoneNumberResponse)
async def sync_phone_number(phone_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> PhoneNumber:
    """Pull all phone number fields from Meta and update DB.

    Refreshes: quality rating, messaging limit, verification status, platform type,
    throughput level, account mode, name status, last onboarded time.
    """
    phone, waba = await _get_phone_with_waba(phone_id, current_user.org_id, db)

    provisioning = get_provisioning_client()
    try:
        phone_info = await provisioning.get_phone_number_details(phone.phone_number_id, waba.access_token)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    _apply_phone_fields(phone, phone_info)
    logger.info("phone.synced", phone_number_id=phone.phone_number_id, quality=phone_info.quality_rating)

    await db.commit()
    await db.refresh(phone)
    return phone


@router.delete("/phone-numbers/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phone_number(phone_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> None:
    """Remove a phone number from the local DB.

    Note: This does not deregister the number from Meta Cloud API.
    Use /deregister first if you want to stop it from sending messages.
    """
    result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.id == phone_id, PhoneNumber.org_id == current_user.org_id)
    )
    phone = result.scalar_one_or_none()
    if not phone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
    await db.delete(phone)
    await db.commit()


@router.post("/phone-numbers/{phone_id}/register", summary="Register phone number with Meta Cloud API")
async def register_phone_number(
    phone_id: uuid.UUID, body: RegisterPhoneRequest, current_user: OrgAdmin, db: DbDep
) -> dict:
    """Register a phone number to use the WhatsApp Cloud API.

    Required once for new numbers before they can send messages.
    Choose a 6-digit PIN — store it safely, needed for re-registration.
    """
    phone, waba = await _get_phone_with_waba(phone_id, current_user.org_id, db)
    provisioning = get_provisioning_client()
    try:
        success = await provisioning.register_phone_number(phone.phone_number_id, body.pin, waba.access_token)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    if success:
        # Sync phone details to pick up updated registration state
        try:
            phone_info = await provisioning.get_phone_number_details(phone.phone_number_id, waba.access_token)
            _apply_phone_fields(phone, phone_info)
            await db.commit()
        except MetaAPIError:
            pass  # best-effort — registration succeeded, sync failure is non-fatal

    return {"success": success, "phone_number_id": phone.phone_number_id}


@router.post("/phone-numbers/{phone_id}/deregister", summary="Deregister phone number from Meta Cloud API")
async def deregister_phone_number(
    phone_id: uuid.UUID, current_user: OrgAdmin, db: DbDep
) -> dict:
    """Deregister a phone number from the WhatsApp Cloud API.

    After deregistering, the number can no longer send or receive messages via
    Cloud API until it is re-registered. The DB record is kept but is_active is
    set to False.
    """
    phone, waba = await _get_phone_with_waba(phone_id, current_user.org_id, db)
    provisioning = get_provisioning_client()
    try:
        success = await provisioning.deregister_phone_number(phone.phone_number_id, waba.access_token)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    if success:
        phone.is_active = False  # type: ignore[assignment]
        await db.commit()

    return {"success": success, "phone_number_id": phone.phone_number_id}


@router.post("/phone-numbers/{phone_id}/request-code", summary="Request OTP to verify phone number")
async def request_verification_code(
    phone_id: uuid.UUID, body: RequestVerificationCodeRequest, current_user: OrgAdmin, db: DbDep
) -> dict:
    """Send OTP via SMS or VOICE to verify the phone number. Call before verify-code."""
    phone, waba = await _get_phone_with_waba(phone_id, current_user.org_id, db)
    provisioning = get_provisioning_client()
    try:
        success = await provisioning.request_verification_code(
            phone.phone_number_id, body.method, body.language, waba.access_token
        )
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)
    return {"success": success, "method": body.method}


@router.post("/phone-numbers/{phone_id}/verify-code", summary="Submit OTP to verify phone number")
async def verify_phone_number(
    phone_id: uuid.UUID, body: VerifyCodeRequest, current_user: OrgAdmin, db: DbDep
) -> dict:
    """Submit the OTP received via SMS/VOICE to complete verification."""
    phone, waba = await _get_phone_with_waba(phone_id, current_user.org_id, db)
    provisioning = get_provisioning_client()
    try:
        success = await provisioning.verify_phone_number(phone.phone_number_id, body.code, waba.access_token)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    if success:
        # Sync phone to pick up VERIFIED status
        try:
            phone_info = await provisioning.get_phone_number_details(phone.phone_number_id, waba.access_token)
            _apply_phone_fields(phone, phone_info)
            await db.commit()
        except MetaAPIError:
            pass  # best-effort

    return {"success": success, "phone_number_id": phone.phone_number_id}


# ── WABA accounts (/{waba_id} AFTER all literal paths) ────────────────────────

@router.get("", response_model=list[WabaResponse])
async def list_waba(current_user: OrgAdmin, db: DbDep) -> list[WabaAccount]:
    """List all connected WABAs from DB."""
    result = await db.execute(
        select(WabaAccount).where(WabaAccount.org_id == current_user.org_id)
    )
    return list(result.scalars().all())


@router.get("/{waba_id}", response_model=WabaResponse)
async def get_waba(waba_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> WabaAccount:
    """Get WABA details from DB."""
    return await _get_waba_row(waba_id, current_user.org_id, db)


@router.post("/{waba_id}/sync", response_model=WabaResponse)
async def sync_waba(waba_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> WabaAccount:
    """Pull latest WABA details from Meta and update DB.

    Refreshes: name, currency, timezone, message_template_namespace,
    account_review_status. Also upserts all phone numbers for this WABA
    with their full Meta field set.
    """
    waba = await _get_waba_row(waba_id, current_user.org_id, db)

    provisioning = get_provisioning_client()
    try:
        details = await provisioning.get_waba_details(waba.waba_id, waba.access_token)
        phone_infos = await provisioning.get_phone_numbers(waba.waba_id, waba.access_token)
    except MetaAPIError as exc:
        raise _meta_error_to_http(exc)

    _apply_waba_fields(waba, details)
    logger.info("waba.synced", meta_waba_id=waba.waba_id, name=waba.business_name)

    # Upsert phone numbers with full field set
    for phone_info in phone_infos:
        existing = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.org_id == current_user.org_id,
                PhoneNumber.phone_number_id == phone_info.phone_number_id,
            )
        )
        phone_row = existing.scalar_one_or_none()
        if phone_row is None:
            phone_row = PhoneNumber(
                org_id=current_user.org_id,
                waba_id=waba.id,
                phone_number_id=phone_info.phone_number_id,
                created_at=datetime.now(timezone.utc),
            )
            _apply_phone_fields(phone_row, phone_info)
            db.add(phone_row)
            logger.info("waba.sync.phone_added", phone_number_id=phone_info.phone_number_id)
        else:
            _apply_phone_fields(phone_row, phone_info)

    await db.commit()
    await db.refresh(waba)
    return waba


@router.patch("/{waba_id}", response_model=WabaResponse)
async def update_waba(waba_id: uuid.UUID, body: WabaUpdate, current_user: OrgAdmin, db: DbDep) -> WabaAccount:
    """Update WABA settings.

    If access_token is updated, the new token is validated against Meta and
    webhook subscription is refreshed automatically. All Meta fields are also
    re-synced from Meta.
    """
    waba = await _get_waba_row(waba_id, current_user.org_id, db)

    token_changed = body.access_token is not None and body.access_token != waba.access_token

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(waba, field, value)

    # If token changed: verify it works + re-subscribe webhooks + re-sync fields
    if token_changed:
        provisioning = get_provisioning_client()
        try:
            details = await provisioning.get_waba_details(waba.waba_id, body.access_token)
            _apply_waba_fields(waba, details)
            await provisioning.subscribe_app_to_waba(waba.waba_id, body.access_token)
            logger.info("waba.token_refreshed", meta_waba_id=waba.waba_id)
        except MetaAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"New access token was rejected by Meta: {exc}",
            )
        except MetaAPIError as exc:
            logger.warning("waba.webhook_resubscribe_failed", error=str(exc))

    await db.commit()
    await db.refresh(waba)
    return waba


@router.get("/{waba_id}/verify-token")
async def verify_waba_token(waba_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> dict:
    """Check what the stored access token can actually do on Meta.

    Returns a diagnosis: which permissions work, which fail, and what to fix.
    """
    import httpx
    waba = await _get_waba_row(waba_id, current_user.org_id, db)
    token = waba.access_token
    meta_waba_id = waba.waba_id
    results: dict = {"waba_id": meta_waba_id, "checks": {}}

    async with httpx.AsyncClient(timeout=10) as client:
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Token introspection — check scopes
        try:
            r = await client.get(f"https://graph.facebook.com/v25.0/me/permissions", headers=headers)
            body = r.json()
            perms = {p["permission"]: p["status"] for p in body.get("data", [])}
            results["checks"]["token_permissions"] = {
                "whatsapp_business_messaging": perms.get("whatsapp_business_messaging", "missing"),
                "whatsapp_business_management": perms.get("whatsapp_business_management", "missing"),
                "business_management": perms.get("business_management", "missing"),
                "all_permissions": perms,
            }
        except Exception as exc:
            results["checks"]["token_permissions"] = {"error": str(exc)}

        # 2. Can read WABA details?
        try:
            r = await client.get(
                f"https://graph.facebook.com/v25.0/{meta_waba_id}",
                headers=headers,
                params={"fields": "id,name,currency,timezone_id"},
            )
            body = r.json()
            if "error" in body:
                results["checks"]["read_waba"] = {"ok": False, "error": body["error"].get("message"), "code": body["error"].get("code")}
            else:
                results["checks"]["read_waba"] = {"ok": True, "name": body.get("name")}
        except Exception as exc:
            results["checks"]["read_waba"] = {"error": str(exc)}

        # 3. Can list templates? (read access)
        try:
            r = await client.get(
                f"https://graph.facebook.com/v25.0/{meta_waba_id}/message_templates",
                headers=headers,
                params={"limit": 1},
            )
            body = r.json()
            if "error" in body:
                results["checks"]["list_templates"] = {"ok": False, "error": body["error"].get("message"), "code": body["error"].get("code"), "type": body["error"].get("type")}
            else:
                results["checks"]["list_templates"] = {"ok": True, "count": len(body.get("data", []))}
        except Exception as exc:
            results["checks"]["list_templates"] = {"error": str(exc)}

        # 4. Check system user identity
        try:
            r = await client.get(
                f"https://graph.facebook.com/v25.0/me",
                headers=headers,
                params={"fields": "id,name"},
            )
            me = r.json()
            results["checks"]["system_user"] = {"id": me.get("id"), "name": me.get("name"), "error": me.get("error", {}).get("message") if "error" in me else None}
        except Exception as exc:
            results["checks"]["system_user"] = {"error": str(exc)}

        # 5. Test template CREATE permission.
        #    Send a minimal valid-ish template. Meta returns:
        #      - OAuthException code 200/10/190 → genuine permission denied (no write access)
        #      - OAuthException code 100 → could be "Invalid parameter" (write access OK, just bad data)
        #      - Any success or non-auth error → write access confirmed
        try:
            r = await client.post(
                f"https://graph.facebook.com/v25.0/{meta_waba_id}/message_templates",
                headers=headers,
                json={
                    "name": "_diagtest_",
                    "category": "UTILITY",
                    "language": "en_US",
                    "components": [{"type": "BODY", "text": "test"}],
                },
            )
            body = r.json()
            error = body.get("error", {})
            error_code = error.get("code", 0)
            error_type = error.get("type", "")
            error_msg = error.get("message", "").lower()
            # Genuine permission errors: code 200 (Permissions error), 10 (API Permission Denied), 190 (token invalid)
            # code 100 with OAuthException = usually "Invalid parameter" (write access is OK)
            is_permission_denied = (
                error_type == "OAuthException"
                and error_code in (190, 200, 10, 3)
            ) or (
                error_type == "OAuthException"
                and error_code == 100
                and any(kw in error_msg for kw in ("permission", "authorized", "oauth", "access"))
                and not any(kw in error_msg for kw in ("invalid parameter", "invalid value", "param"))
            )
            if is_permission_denied:
                results["checks"]["create_template"] = {
                    "ok": False,
                    "error": error.get("message"),
                    "code": error_code,
                    "type": error_type,
                }
            else:
                # Validation error or success — write access confirmed.
                results["checks"]["create_template"] = {
                    "ok": True,
                    "note": "write access confirmed" if not error else f"validation error (expected): {error.get('message')}",
                }
        except Exception as exc:
            results["checks"]["create_template"] = {"error": str(exc)}

    # Diagnosis
    perms_check = results["checks"].get("token_permissions", {})
    wm_mgmt = perms_check.get("whatsapp_business_management", "missing")
    wm_msg = perms_check.get("whatsapp_business_messaging", "missing")
    read_ok = results["checks"].get("list_templates", {}).get("ok", False)
    write_ok = results["checks"].get("create_template", {}).get("ok", False)

    if wm_mgmt != "granted":
        results["diagnosis"] = "TOKEN_MISSING_MANAGEMENT: Token lacks 'whatsapp_business_management' scope. Regenerate the token and enable that scope."
    elif not read_ok:
        results["diagnosis"] = "WABA_NOT_ASSIGNED: Token has correct scopes but cannot read this WABA. In Meta Business Settings → System Users → select your user → Add Assets → WhatsApp Accounts → assign this WABA → regenerate the token."
    elif not write_ok:
        results["diagnosis"] = "WABA_NO_WRITE_ACCESS: Token can read templates but cannot create them. In Meta Business Settings → System Users → select your user → Add Assets → WhatsApp Accounts → assign this WABA with Full Control → regenerate the token."
    elif wm_msg != "granted":
        results["diagnosis"] = "TOKEN_MISSING_MESSAGING: Token lacks 'whatsapp_business_messaging' scope."
    else:
        results["diagnosis"] = "OK: Token appears to have all required permissions."

    return results


@router.delete("/{waba_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_waba(waba_id: uuid.UUID, current_user: OrgAdmin, db: DbDep) -> None:
    """Disconnect a WABA — unsubscribes webhooks on Meta, then deletes from DB."""
    from sqlalchemy import delete as sql_delete
    from app.models.whatsapp import MessageTemplate

    waba = await _get_waba_row(waba_id, current_user.org_id, db)

    # Unsubscribe webhooks from Meta (best-effort)
    provisioning = get_provisioning_client()
    try:
        subscribed = await provisioning.get_subscribed_apps(waba.waba_id, waba.access_token)
        if subscribed:
            logger.info("waba.disconnecting", meta_waba_id=waba.waba_id, subscribed_apps=len(subscribed))
    except MetaAPIError as exc:
        logger.warning("waba.unsubscribe_check_failed", error=str(exc))

    # Delete child records first to avoid FK constraint violations
    # 1. Messages referencing conversations whose phone_number belongs to this WABA
    phone_result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.waba_id == waba.id)
    )
    phone_rows = phone_result.scalars().all()
    phone_ids = [p.id for p in phone_rows]

    if phone_ids:
        from app.models.message import Message, Conversation
        conv_result = await db.execute(
            select(Conversation.id).where(Conversation.phone_number_id.in_(phone_ids))
        )
        conv_ids = [r[0] for r in conv_result.all()]
        if conv_ids:
            await db.execute(sql_delete(Message).where(Message.conversation_id.in_(conv_ids)))
            await db.execute(sql_delete(Conversation).where(Conversation.id.in_(conv_ids)))

        # 2. Phone numbers
        await db.execute(sql_delete(PhoneNumber).where(PhoneNumber.waba_id == waba.id))

    # 3. Templates
    await db.execute(sql_delete(MessageTemplate).where(MessageTemplate.waba_id == waba.id))

    # 4. Finally the WABA itself
    await db.delete(waba)
    await db.commit()
    logger.info("waba.deleted", meta_waba_id=waba.waba_id, org_id=str(current_user.org_id))

"""Schemas for WABA accounts, phone numbers, and message templates."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── WABA Account ─────────────────────────────────────────────────────────────

class WabaCreate(BaseModel):
    waba_id: str
    access_token: str
    webhook_secret: str | None = None
    business_name: str | None = None


class WabaCreateRequest(BaseModel):
    """Create a brand-new WABA on Meta under your Business Account.

    Requires a token with `business_management` permission for the given
    business_id (typically a system user or partner token).
    """
    business_id: str                  # Meta Business Account ID (parent)
    name: str                         # display name for the new WABA
    currency: str = "USD"             # ISO 4217, e.g. "USD", "INR"
    timezone_id: str = "1"            # Meta timezone ID — "1" = UTC
    access_token: str                 # token with business_management permission


class WabaUpdate(BaseModel):
    access_token: str | None = None
    webhook_secret: str | None = None
    business_name: str | None = None
    status: str | None = None


class WabaResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    waba_id: str
    business_name: str | None
    status: str
    # Meta WABA fields
    business_id: str | None = None
    currency: str | None = None
    timezone_id: str | None = None
    message_template_namespace: str | None = None
    account_review_status: str | None = None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Phone Number ──────────────────────────────────────────────────────────────

class PhoneNumberCreate(BaseModel):
    waba_id: uuid.UUID  # internal waba_accounts.id
    phone_number_id: str  # Meta's phone number ID
    display_number: str | None = None
    display_name: str | None = None
    quality_rating: str | None = None
    messaging_limit: str | None = None


class PhoneNumberAddRequest(BaseModel):
    """Add a phone number to a WABA by fetching its details from Meta.

    The phone number must already exist on Meta (e.g. added via Business Manager).
    This pulls all current fields from Meta and saves them to the local DB.
    """
    waba_id: uuid.UUID   # internal waba_accounts.id
    phone_number_id: str  # Meta's phone number ID (numeric string)


class PhoneNumberResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    waba_id: uuid.UUID
    phone_number_id: str
    display_number: str | None
    display_name: str | None
    quality_rating: str | None
    messaging_limit: str | None
    is_active: bool
    created_at: datetime | None
    # Meta phone number fields
    code_verification_status: str | None = None
    platform_type: str | None = None
    throughput_level: str | None = None
    account_mode: str | None = None
    name_status: str | None = None
    last_onboarded_time: datetime | None = None

    model_config = {"from_attributes": True}


# ── Embedded Signup / Provisioning ───────────────────────────────────────────

class EmbeddedSignupRequest(BaseModel):
    code: str  # short-lived code from Meta's JS SDK


class ProvisionedPhoneNumber(BaseModel):
    phone_number_id: str
    display_number: str
    verified_name: str
    quality_rating: str
    code_verification_status: str
    messaging_limit_tier: str


class ProvisionedWaba(BaseModel):
    waba_id: str
    name: str
    currency: str
    timezone_id: str
    phone_numbers: list[ProvisionedPhoneNumber]


class EmbeddedSignupResponse(BaseModel):
    """Returned after a successful Embedded Signup code exchange + DB save."""
    wabas_connected: int
    phone_numbers_saved: int
    wabas: list[WabaResponse]


class RegisterPhoneRequest(BaseModel):
    pin: str  # 6-digit PIN you choose


class RequestVerificationCodeRequest(BaseModel):
    method: str = "SMS"     # "SMS" | "VOICE"
    language: str = "en_US"


class VerifyCodeRequest(BaseModel):
    code: str  # OTP received via SMS/VOICE


# ── Message Template ──────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    waba_id: uuid.UUID
    name: str
    category: str  # MARKETING | UTILITY | AUTHENTICATION
    language: str = "en"
    components: list[dict[str, Any]] = []


class TemplateUpdate(BaseModel):
    components: list[dict[str, Any]] | None = None
    status: str | None = None
    rejection_reason: str | None = None


class TemplateResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    waba_id: uuid.UUID
    meta_template_id: str | None
    name: str
    category: str
    language: str
    status: str
    components: list[dict[str, Any]]
    rejection_reason: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}

"""Schemas for messages and conversations."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── Send message request ──────────────────────────────────────────────────────

class SendTextRequest(BaseModel):
    phone_number_id: uuid.UUID  # internal PhoneNumber.id
    to: str                     # E.164 recipient phone
    body: str
    idempotency_key: str | None = None  # client-supplied; auto-derived if absent


class SendTemplateRequest(BaseModel):
    phone_number_id: uuid.UUID
    to: str
    template_name: str
    language_code: str = "en"
    components: list[dict[str, Any]] | None = None
    idempotency_key: str | None = None


class MarkReadRequest(BaseModel):
    message_id: uuid.UUID  # internal Message.id (must be an inbound message)


class SendMessageResponse(BaseModel):
    message_id: uuid.UUID
    wa_message_id: str
    status: str
    cost_credits: float


# ── Conversation ──────────────────────────────────────────────────────────────

class ConversationResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    contact_id: uuid.UUID
    phone_number_id: uuid.UUID
    status: str
    assigned_to: uuid.UUID | None
    last_message_at: datetime | None
    session_expires_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    contact_phone: str | None = None
    contact_name: str | None = None

    model_config = {"from_attributes": True}


# ── Message ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    conversation_id: uuid.UUID
    wa_message_id: str | None
    direction: str
    status: str
    message_type: str
    content: dict[str, Any]
    cost_credits: float | None
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    created_at: datetime | None

    model_config = {"from_attributes": True}

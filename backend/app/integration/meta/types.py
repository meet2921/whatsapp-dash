"""Typed dataclasses for Meta Cloud API payloads.

All inbound webhook data is normalised into these types by MetaWebhook.parse().
All outbound send results are returned as SendResult.

No ORM / Pydantic dependency — plain dataclasses so this package stays
portable and independently testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Outbound results ──────────────────────────────────────────────────────────

@dataclass
class SendResult:
    """Returned by every MetaClient.send_*() method."""
    wa_message_id: str        # e.g. "wamid.HBgLOTE4NzY1..."
    recipient_phone: str      # E.164 without +, e.g. "919876543210"
    status: str               # always "accepted" on success
    raw: dict = field(default_factory=dict)


# ── Inbound webhook payloads ──────────────────────────────────────────────────

@dataclass
class InboundMessage:
    """A single inbound WhatsApp message from a user."""
    wa_message_id: str        # Meta's wamid — use for idempotency
    from_phone: str           # sender E.164 without +
    timestamp: int            # Unix epoch seconds
    message_type: str         # text | image | audio | video | document |
                              # sticker | button | interactive | location | contacts | reaction

    # Type-specific payloads (only one is set per message)
    text: str | None = None                   # message_type == "text"
    media: dict[str, Any] | None = None       # image/audio/video/document/sticker
    button: dict[str, Any] | None = None      # quick-reply button tap
    interactive: dict[str, Any] | None = None # list/cta-url reply
    location: dict[str, Any] | None = None    # location share
    contacts: list[dict[str, Any]] | None = None  # contact card
    reaction: dict[str, Any] | None = None    # emoji reaction

    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def display_text(self) -> str:
        """Best-effort human-readable summary for logging."""
        if self.text:
            return self.text[:80]
        if self.button:
            return f"[button] {self.button.get('text', '')}"
        if self.interactive:
            t = self.interactive.get("type", "")
            return f"[interactive:{t}]"
        return f"[{self.message_type}]"


@dataclass
class StatusUpdate:
    """Delivery/read status update for an outbound message."""
    wa_message_id: str        # the outbound wamid
    recipient_phone: str
    status: str               # sent | delivered | read | failed | deleted
    timestamp: int
    conversation_id: str | None = None     # Meta's conversation window ID
    conversation_origin: str | None = None # marketing | utility | authentication | service
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def error_code(self) -> int | None:
        if self.errors:
            return self.errors[0].get("code")
        return None

    @property
    def error_message(self) -> str | None:
        if self.errors:
            return self.errors[0].get("message")
        return None


@dataclass
class TemplateStatusUpdate:
    """Template approval / rejection / pause notification from Meta."""
    message_template_id: str
    message_template_name: str
    message_template_language: str
    event: str                # APPROVED | REJECTED | DISABLED | FLAGGED |
                              # REINSTATED | PAUSED | PENDING_DELETION
    reason: str | None = None # rejection/pause reason
    waba_id: str = ""


@dataclass
class ParsedWebhookChange:
    """One parsed 'change' object from a Meta webhook entry."""
    phone_number_id: str      # Meta phone number ID (maps to phone_numbers table)
    waba_id: str              # Meta WABA ID (maps to waba_accounts table)
    messages: list[InboundMessage] = field(default_factory=list)
    statuses: list[StatusUpdate] = field(default_factory=list)
    template_updates: list[TemplateStatusUpdate] = field(default_factory=list)


@dataclass
class ParsedWebhookPayload:
    """Top-level result of MetaWebhook.parse(raw_dict)."""
    changes: list[ParsedWebhookChange] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return all(
            not c.messages and not c.statuses and not c.template_updates
            for c in self.changes
        )

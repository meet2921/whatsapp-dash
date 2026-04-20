"""Meta webhook verification and payload parsing.

Usage:
    from app.integration.meta import MetaWebhook

    # Verify (raises MetaWebhookSignatureError on failure)
    MetaWebhook.verify_signature(app_secret, raw_body, request.headers.get("X-Hub-Signature-256", ""))

    # Parse
    payload = MetaWebhook.parse(json.loads(raw_body))
    for change in payload.changes:
        for msg in change.messages:
            print(msg.from_phone, msg.text)
"""
import hashlib
import hmac
from typing import Any

from app.integration.meta.exceptions import MetaWebhookSignatureError
from app.integration.meta.types import (
    InboundMessage,
    ParsedWebhookChange,
    ParsedWebhookPayload,
    StatusUpdate,
    TemplateStatusUpdate,
)


class MetaWebhook:
    """Stateless utility class — all methods are static."""

    # ── Signature verification ─────────────────────────────────────────────────

    @staticmethod
    def verify_signature(app_secret: str, raw_body: bytes, signature_header: str) -> None:
        """Verify the X-Hub-Signature-256 HMAC-SHA256 signature.

        Args:
            app_secret: META_APP_SECRET from .env (App Dashboard → Settings → Basic)
            raw_body:   Raw request bytes (before JSON parsing)
            signature_header: Value of X-Hub-Signature-256 header

        Raises:
            MetaWebhookSignatureError: if signature does not match or header is missing
        """
        if not app_secret:
            # App secret not configured — skip verification (dev mode only)
            return

        if not signature_header:
            raise MetaWebhookSignatureError(
                "Missing X-Hub-Signature-256 header — request may not be from Meta"
            )

        expected = "sha256=" + hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature_header, expected):
            raise MetaWebhookSignatureError(
                "X-Hub-Signature-256 mismatch — invalid signature"
            )

    # ── Payload parsing ────────────────────────────────────────────────────────

    @staticmethod
    def parse(raw: dict[str, Any]) -> ParsedWebhookPayload:
        """Parse a full Meta webhook POST body into typed objects.

        Meta payload structure:
        {
          "object": "whatsapp_business_account",
          "entry": [
            {
              "id": "<WABA_ID>",
              "changes": [
                {
                  "field": "messages",
                  "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "...", "display_phone_number": "..."},
                    "contacts": [...],
                    "messages": [...],
                    "statuses": [...]
                  }
                }
              ]
            }
          ]
        }
        """
        changes: list[ParsedWebhookChange] = []

        for entry in raw.get("entry", []):
            waba_id = entry.get("id", "")

            for change in entry.get("changes", []):
                field_name = change.get("field", "")
                value = change.get("value", {})

                if field_name == "messages":
                    parsed = MetaWebhook._parse_messages_change(waba_id, value)
                    changes.append(parsed)

                elif field_name == "message_template_status_update":
                    # Template approval/rejection comes as a top-level change
                    tsu = MetaWebhook._parse_template_status(value, waba_id)
                    changes.append(ParsedWebhookChange(
                        phone_number_id="",
                        waba_id=waba_id,
                        template_updates=[tsu] if tsu else [],
                    ))

        return ParsedWebhookPayload(changes=changes, raw=raw)

    @staticmethod
    def _parse_messages_change(waba_id: str, value: dict) -> ParsedWebhookChange:
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id", "")

        messages = [
            MetaWebhook._parse_inbound_message(m)
            for m in value.get("messages", [])
        ]
        statuses = [
            MetaWebhook._parse_status_update(s)
            for s in value.get("statuses", [])
        ]

        return ParsedWebhookChange(
            phone_number_id=phone_number_id,
            waba_id=waba_id,
            messages=messages,
            statuses=statuses,
        )

    @staticmethod
    def _parse_inbound_message(raw: dict) -> InboundMessage:
        msg_type = raw.get("type", "text")

        # Extract type-specific payload
        text: str | None = None
        media: dict | None = None
        button: dict | None = None
        interactive: dict | None = None
        location: dict | None = None
        contacts: list | None = None
        reaction: dict | None = None

        if msg_type == "text":
            text = raw.get("text", {}).get("body", "")

        elif msg_type in ("image", "audio", "video", "document", "sticker"):
            raw_media = raw.get(msg_type, {})
            media = {
                "id": raw_media.get("id"),
                "mime_type": raw_media.get("mime_type"),
                "sha256": raw_media.get("sha256"),
                "caption": raw_media.get("caption"),
                "filename": raw_media.get("filename"),  # documents only
            }

        elif msg_type == "button":
            raw_btn = raw.get("button", {})
            button = {
                "text": raw_btn.get("text"),
                "payload": raw_btn.get("payload"),
            }

        elif msg_type == "interactive":
            raw_int = raw.get("interactive", {})
            interactive_type = raw_int.get("type", "")
            if interactive_type == "button_reply":
                interactive = {
                    "type": "button_reply",
                    "id": raw_int.get("button_reply", {}).get("id"),
                    "title": raw_int.get("button_reply", {}).get("title"),
                }
            elif interactive_type == "list_reply":
                interactive = {
                    "type": "list_reply",
                    "id": raw_int.get("list_reply", {}).get("id"),
                    "title": raw_int.get("list_reply", {}).get("title"),
                    "description": raw_int.get("list_reply", {}).get("description"),
                }
            else:
                interactive = raw_int

        elif msg_type == "location":
            raw_loc = raw.get("location", {})
            location = {
                "latitude": raw_loc.get("latitude"),
                "longitude": raw_loc.get("longitude"),
                "name": raw_loc.get("name"),
                "address": raw_loc.get("address"),
            }

        elif msg_type == "contacts":
            contacts = raw.get("contacts", [])

        elif msg_type == "reaction":
            raw_react = raw.get("reaction", {})
            reaction = {
                "message_id": raw_react.get("message_id"),
                "emoji": raw_react.get("emoji"),
            }

        return InboundMessage(
            wa_message_id=raw.get("id", ""),
            from_phone=raw.get("from", ""),
            timestamp=int(raw.get("timestamp", 0)),
            message_type=msg_type,
            text=text,
            media=media,
            button=button,
            interactive=interactive,
            location=location,
            contacts=contacts,
            reaction=reaction,
            raw=raw,
        )

    @staticmethod
    def _parse_status_update(raw: dict) -> StatusUpdate:
        conversation = raw.get("conversation", {})
        origin = conversation.get("origin", {})

        return StatusUpdate(
            wa_message_id=raw.get("id", ""),
            recipient_phone=raw.get("recipient_id", ""),
            status=raw.get("status", ""),
            timestamp=int(raw.get("timestamp", 0)),
            conversation_id=conversation.get("id"),
            conversation_origin=origin.get("type"),
            errors=raw.get("errors", []),
        )

    @staticmethod
    def _parse_template_status(raw: dict, waba_id: str = "") -> TemplateStatusUpdate | None:
        if not raw:
            return None
        return TemplateStatusUpdate(
            message_template_id=str(raw.get("message_template_id", "")),
            message_template_name=raw.get("message_template_name", ""),
            message_template_language=raw.get("message_template_language", ""),
            event=raw.get("event", ""),
            reason=raw.get("reason"),
            waba_id=waba_id,
        )

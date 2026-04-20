"""Meta Cloud API exception hierarchy.

Callers should catch MetaAPIError for general errors.
Use specific subclasses for targeted handling:
  MetaTransientError  → retry (Tenacity handles this automatically)
  MetaRateLimitError  → back off and retry later
  MetaAuthError       → token expired, alert org admin
  MetaWebhookSignatureError → security violation, reject request immediately
"""


class MetaAPIError(Exception):
    """Base for all Meta Cloud API errors (4xx / 5xx with error body)."""

    def __init__(self, status_code: int, error_body: dict) -> None:
        self.status_code = status_code
        self.error_body = error_body
        # Meta error body: {"error": {"code": 190, "message": "...", "type": "OAuthException"}}
        err = error_body.get("error", {})
        self.error_code: int = err.get("code", 0)
        self.error_type: str = err.get("type", "")
        self.error_message: str = err.get("message", str(error_body))
        # Extra detail fields Meta includes for validation errors
        extra = " | ".join(filter(None, [
            err.get("error_data"),
            err.get("error_user_msg"),
            str(err["error_subcode"]) if err.get("error_subcode") else None,
        ]))
        detail = f": {extra}" if extra else ""
        super().__init__(
            f"Meta API {status_code} (code={self.error_code}, type={self.error_type}): {self.error_message}{detail}"
        )


class MetaTransientError(MetaAPIError):
    """HTTP 5xx or transient network failure — safe to retry with backoff.

    Tenacity in MetaClient retries these automatically.
    """


class MetaRateLimitError(MetaAPIError):
    """HTTP 429 — Meta is rate-limiting this phone number.

    Meta error code 130429 = rate limit exceeded.
    Back off for at least 60 seconds before retrying.
    """


class MetaAuthError(MetaAPIError):
    """HTTP 401/403 — access token expired or insufficient permission.

    Meta error codes:
      190  = OAuthException (token invalid/expired)
      200  = Permission error
      100  = Invalid parameter (often a bad WABA/phone ID)

    Resolution: org admin must refresh their System User Token.
    """


class MetaWebhookSignatureError(Exception):
    """X-Hub-Signature-256 header does not match computed HMAC.

    Indicates either:
      1. Wrong META_APP_SECRET in .env
      2. Request tampered in transit
      3. Genuine attack — reject immediately, log IP
    """

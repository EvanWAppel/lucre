"""Email sending via Resend's HTTP API.

A thin wrapper so the rest of the app depends only on `send(subject, html)`. Tests
use tests.conftest.FakeEmailClient instead of touching the network.
"""

import logging
from typing import Protocol

import httpx

from config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT = 10.0


class EmailClientLike(Protocol):
    """What the app needs from an email client; FakeEmailClient satisfies it too."""

    def send(self, subject: str, html: str) -> None: ...


class ResendEmailClient:
    """Sends one-off HTML emails through Resend. Failures are logged loudly and
    re-raised — never swallowed."""

    def __init__(self) -> None:
        self._api_key = settings.resend_api_key
        self._from = settings.alert_from_email
        self._to = settings.alert_to_email

    def send(self, subject: str, html: str) -> None:
        payload = {"from": self._from, "to": [self._to], "subject": subject, "html": html}
        try:
            response = httpx.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Resend email send failed: subject=%r", subject)
            raise
        logger.info("Sent email: %r", subject)


_client: ResendEmailClient | None = None


def get_email_client() -> ResendEmailClient:
    """FastAPI dependency / scheduler helper. Overridden with FakeEmailClient in tests."""
    global _client
    if _client is None:
        _client = ResendEmailClient()
    return _client

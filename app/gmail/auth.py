from __future__ import annotations

import logging
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.config import GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_cached_token: str | None = None
_cached_expiry: float = 0.0


def _credentials() -> Credentials | None:
    if not (GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN):
        return None
    return Credentials(
        token=None,
        refresh_token=GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )


def get_access_token() -> str | None:
    """Return a valid Gmail API access token, refreshing when needed."""
    global _cached_token, _cached_expiry

    creds = _credentials()
    if creds is None:
        logger.error("Gmail OAuth credentials are not configured")
        return None

    now = time.time()
    if _cached_token and now < _cached_expiry - 60:
        return _cached_token

    creds.refresh(Request())
    if not creds.token:
        logger.error("Gmail token refresh returned no access token")
        return None

    _cached_token = creds.token
    expiry = creds.expiry.timestamp() if creds.expiry else now + 3500
    _cached_expiry = expiry
    return _cached_token

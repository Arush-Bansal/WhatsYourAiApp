import hashlib
import hmac
import logging
import time

from fastapi import HTTPException

from app.config import GMAIL_PUSH_AUDIENCE, GMAIL_WATCH_SECRET, SLACK_SIGNING_SECRET, WHATSAPP_APP_SECRET

logger = logging.getLogger(__name__)

SLACK_SIGNATURE_MAX_AGE_SECONDS = 60 * 5


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> None:
    if not WHATSAPP_APP_SECRET:
        return
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="Missing or invalid signature")
    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="Invalid signature")


def verify_slack_signature(
    raw_body: bytes,
    signature_header: str | None,
    timestamp_header: str | None,
) -> None:
    if not SLACK_SIGNING_SECRET:
        return
    if not signature_header or not signature_header.startswith("v0="):
        raise HTTPException(status_code=403, detail="Missing or invalid Slack signature")
    if not timestamp_header:
        raise HTTPException(status_code=403, detail="Missing Slack request timestamp")
    try:
        request_ts = int(timestamp_header)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid Slack request timestamp") from exc
    if abs(time.time() - request_ts) > SLACK_SIGNATURE_MAX_AGE_SECONDS:
        raise HTTPException(status_code=403, detail="Stale Slack request timestamp")
    sig_basestring = f"v0:{timestamp_header}:{raw_body.decode('utf-8')}"
    expected = (
        "v0="
        + hmac.new(
            SLACK_SIGNING_SECRET.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")


def _pubsub_audience_candidates() -> list[str]:
    """Audience strings to try (Pub/Sub default is the push endpoint URL)."""
    raw = (GMAIL_PUSH_AUDIENCE or "").strip()
    if not raw:
        return []
    trimmed = raw.rstrip("/")
    candidates = [raw, trimmed, f"{trimmed}/"]
    seen: set[str] = set()
    out: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def verify_pubsub_push(authorization_header: str | None) -> None:
    """Validate the OIDC token sent by Google Pub/Sub push subscriptions."""
    if not GMAIL_PUSH_AUDIENCE:
        return
    if not authorization_header or not authorization_header.startswith("Bearer "):
        logger.warning(
            "Pub/Sub push rejected: no Bearer token. Either enable authentication on the "
            "Pub/Sub push subscription (with audience=%r) or unset GMAIL_PUSH_AUDIENCE.",
            GMAIL_PUSH_AUDIENCE,
        )
        raise HTTPException(status_code=403, detail="Missing or invalid Pub/Sub authorization")
    token = authorization_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=403, detail="Missing Pub/Sub authorization token")
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        request = google_requests.Request()
        last_error: ValueError | None = None
        for audience in _pubsub_audience_candidates():
            try:
                id_token.verify_oauth2_token(token, request, audience=audience)
                return
            except ValueError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
    except ValueError as exc:
        logger.warning(
            "Pub/Sub push rejected: JWT verification failed (%s). "
            "Ensure GMAIL_PUSH_AUDIENCE matches the subscription audience "
            "(default is the push endpoint URL exactly).",
            exc,
        )
        raise HTTPException(status_code=403, detail="Invalid Pub/Sub token") from exc


def verify_gmail_watch_secret(header_value: str | None) -> None:
    if not GMAIL_WATCH_SECRET:
        return
    if not header_value or not hmac.compare_digest(header_value, GMAIL_WATCH_SECRET):
        raise HTTPException(status_code=403, detail="Invalid Gmail watch secret")

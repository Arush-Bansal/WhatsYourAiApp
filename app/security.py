import hashlib
import hmac
import time

from fastapi import HTTPException

from app.config import SLACK_SIGNING_SECRET, WHATSAPP_APP_SECRET

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

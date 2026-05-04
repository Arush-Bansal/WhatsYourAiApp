import hashlib
import hmac

from fastapi import HTTPException

from app.config import WHATSAPP_APP_SECRET


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

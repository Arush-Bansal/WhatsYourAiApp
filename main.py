import hashlib
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
PROCESSED_IDS_MAX = 2000

_verify_token = os.getenv("VERIFY_TOKEN", "")
_access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
_default_phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
_app_secret = os.getenv("WHATSAPP_APP_SECRET", "")

_processed_message_ids: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=30.0) as client:
        app.state.http = client
        yield


app = FastAPI(lifespan=lifespan, title="WhatsApp webhook")


def _trim_processed_ids() -> None:
    if len(_processed_message_ids) > PROCESSED_IDS_MAX:
        _processed_message_ids.clear()


def _verify_meta_signature(raw_body: bytes, signature_header: str | None) -> None:
    if not _app_secret:
        return
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="Missing or invalid signature")
    expected = hmac.new(
        _app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="Invalid signature")


async def _send_text_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    body: str,
) -> None:
    if not _access_token:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot send reply")
        return
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    headers = {"Authorization": f"Bearer {_access_token}"}
    resp = await http.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "Graph API error: %s %s",
            resp.status_code,
            resp.text[:500],
        )


def _iter_incoming_text_messages(data: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """
    Returns list of (message_id, from_wa_id, text_body, phone_number_id).
    """
    out: list[tuple[str, str, str, str]] = []
    if data.get("object") != "whatsapp_business_account":
        return out
    for entry in data.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(
                metadata.get("phone_number_id") or _default_phone_number_id or ""
            )
            for msg in value.get("messages") or []:
                if msg.get("type") != "text":
                    continue
                text = (msg.get("text") or {}).get("body")
                if text is None:
                    continue
                mid = str(msg.get("id") or "")
                from_id = str(msg.get("from") or "")
                if mid and from_id and phone_number_id:
                    out.append((mid, from_id, str(text), phone_number_id))
    return out


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "whatsapp-webhook",
        "wake": "/wake",
        "webhook": "/webhook",
    }


@app.get("/wake")
async def wake() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid hub.mode")
    if not _verify_token or hub_verify_token != _verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    if hub_challenge is None:
        raise HTTPException(status_code=400, detail="Missing hub.challenge")
    return Response(content=hub_challenge, media_type="text/plain")


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, str]:
    raw = await request.body()
    try:
        _verify_meta_signature(raw, request.headers.get("x-hub-signature-256"))
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        logger.warning("Webhook POST: invalid JSON")
        return {"status": "ok"}
    except HTTPException:
        raise

    http: httpx.AsyncClient = request.app.state.http

    for message_id, from_wa_id, text_body, phone_number_id in _iter_incoming_text_messages(
        data
    ):
        if message_id in _processed_message_ids:
            continue
        _processed_message_ids.add(message_id)
        _trim_processed_ids()

        if text_body.strip().lower() != "hi":
            continue

        await _send_text_reply(http, phone_number_id, from_wa_id, "hi")

    return {"status": "ok"}

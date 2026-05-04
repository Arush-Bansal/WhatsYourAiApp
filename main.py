import hashlib
import hmac
import html
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

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


async def _send_interactive_buttons_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    body_text: str = "Tap a button - demo reply.",
) -> None:
    if not _access_token:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot send reply")
        return
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "demo_ok", "title": "Sounds good"}},
                    {"type": "reply", "reply": {"id": "demo_later", "title": "Not now"}},
                    {"type": "reply", "reply": {"id": "demo_info", "title": "More info"}},
                ]
            },
        },
    }
    headers = {"Authorization": f"Bearer {_access_token}"}
    resp = await http.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "Graph API error (interactive): %s %s",
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


def _iter_incoming_button_replies(
    data: dict[str, Any],
) -> list[tuple[str, str, str, str, str]]:
    """
    Returns list of (message_id, from_wa_id, button_id, button_title, phone_number_id)
    for interactive quick-reply button taps.
    """
    out: list[tuple[str, str, str, str, str]] = []
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
                if msg.get("type") != "interactive":
                    continue
                inter = msg.get("interactive") or {}
                if inter.get("type") != "button_reply":
                    continue
                br = inter.get("button_reply") or {}
                bid = str(br.get("id") or "")
                title = str(br.get("title") or "")
                mid = str(msg.get("id") or "")
                from_id = str(msg.get("from") or "")
                if mid and from_id and phone_number_id and (bid or title):
                    out.append((mid, from_id, bid, title, phone_number_id))
    return out


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "whatsapp-webhook",
        "wake": "/wake",
        "webhook": "/webhook",
        "demo_buttons": "/demo/buttons",
        "demo_form": "/demo/form",
    }


_DEMO_PAGE_STYLE = """
:root { font-family: system-ui, sans-serif; background: #0f1419; color: #e6edf3; }
body { max-width: 28rem; margin: 2rem auto; padding: 0 1rem; }
.card {
  background: #161b22; border: 1px solid #30363d; border-radius: 12px;
  padding: 1.25rem; margin-bottom: 1rem;
}
.msg { font-size: 1rem; line-height: 1.5; margin-bottom: 1rem; }
.row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
button, .btn {
  cursor: pointer; border: none; border-radius: 8px; padding: 0.6rem 1rem;
  font-size: 0.95rem; background: #238636; color: #fff;
}
button.secondary { background: #21262d; color: #e6edf3; border: 1px solid #30363d; }
button.ghost { background: transparent; border: 1px solid #388bfd; color: #58a6ff; }
label { display: block; margin: 0.75rem 0 0.35rem; font-size: 0.9rem; color: #8b949e; }
input[type="text"], select {
  width: 100%; box-sizing: border-box; padding: 0.5rem 0.6rem;
  border-radius: 8px; border: 1px solid #30363d; background: #0d1117; color: #e6edf3;
}
select[multiple] { min-height: 8rem; }
a { color: #58a6ff; }
"""


@app.get("/demo/buttons", response_class=HTMLResponse)
async def demo_buttons() -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Buttons demo</title>
  <style>{_DEMO_PAGE_STYLE}</style>
</head>
<body>
  <div class="card">
    <div class="msg" id="msg">Choose an option below.</div>
    <div class="row">
      <button type="button" onclick="setMsg('You picked: Confirm')">Confirm</button>
      <button type="button" class="secondary" onclick="setMsg('You picked: Snooze')">Snooze</button>
      <button type="button" class="ghost" onclick="setMsg('You picked: Details')">Details</button>
    </div>
  </div>
  <p><a href="/">Back to API root</a></p>
  <script>
    function setMsg(t) {{ document.getElementById('msg').textContent = t; }}
  </script>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/demo/form", response_class=HTMLResponse)
async def demo_form_get() -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Multiselect form demo</title>
  <style>{_DEMO_PAGE_STYLE}</style>
</head>
<body>
  <div class="card">
    <h1 style="font-size:1.1rem;margin:0 0 1rem;">Notify me about</h1>
    <form method="post" action="/demo/form">
      <label for="name">Name</label>
      <input type="text" id="name" name="name" placeholder="Ada" required />
      <label for="topics">Topics (hold Ctrl or Cmd to pick several)</label>
      <select id="topics" name="topics" multiple>
        <option value="product">Product updates</option>
        <option value="events">Events</option>
        <option value="beta">Beta program</option>
        <option value="security">Security alerts</option>
      </select>
      <div class="row" style="margin-top:1rem;">
        <button type="submit" class="btn">Submit</button>
      </div>
    </form>
  </div>
  <p><a href="/">Back to API root</a></p>
</body>
</html>"""
    return HTMLResponse(html)


@app.post("/demo/form", response_class=HTMLResponse)
async def demo_form_post(
    name: str = Form(...),
    topics: list[str] = Form(default_factory=list),
) -> HTMLResponse:
    chosen = ", ".join(topics) if topics else "(none selected)"
    safe_name = html.escape(name)
    safe_chosen = html.escape(chosen)
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Submitted</title>
  <style>{_DEMO_PAGE_STYLE}</style>
</head>
<body>
  <div class="card">
    <div class="msg">Thanks, <strong>{safe_name}</strong>.</div>
    <p style="margin:0;color:#8b949e;">You selected: <strong>{safe_chosen}</strong></p>
  </div>
  <p><a href="/demo/form">Submit again</a> · <a href="/">API root</a></p>
</body>
</html>"""
    return HTMLResponse(page)


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

    for message_id, from_wa_id, bid, title, phone_number_id in _iter_incoming_button_replies(
        data
    ):
        if message_id in _processed_message_ids:
            continue
        _processed_message_ids.add(message_id)
        _trim_processed_ids()
        ack = f'You tapped "{title}"' + (f" (id: {bid})" if bid else "") + "."
        await _send_text_reply(http, phone_number_id, from_wa_id, ack)

    for message_id, from_wa_id, text_body, phone_number_id in _iter_incoming_text_messages(
        data
    ):
        if message_id in _processed_message_ids:
            continue
        _processed_message_ids.add(message_id)
        _trim_processed_ids()

        if text_body.strip().lower() == "buttons":
            await _send_interactive_buttons_reply(
                http,
                phone_number_id,
                from_wa_id,
                body_text="Here are quick-reply buttons. Tap one.",
            )
        else:
            reply = f'You typed: "{text_body}"'
            await _send_text_reply(http, phone_number_id, from_wa_id, reply)

    return {"status": "ok"}

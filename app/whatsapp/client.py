import json
import logging
from typing import Any

import httpx

from app.config import GRAPH_API_VERSION, WHATSAPP_ACCESS_TOKEN
from app.whatsapp.payloads import (
    InteractiveButtonsPayload,
    InteractiveListPayload,
)

logger = logging.getLogger(__name__)


async def send_text_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    body: str,
) -> bool:
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot send reply")
        return False
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    resp = await http.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "Graph API error: %s %s",
            resp.status_code,
            resp.text[:500],
        )
        return False
    return True


async def download_whatsapp_media(
    http: httpx.AsyncClient,
    media_id: str,
) -> tuple[bytes, str | None] | None:
    """Resolve media_id via Graph API and download bytes. Returns (body, mime_type) or None on failure."""
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot download media")
        return None
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    meta_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
    meta_resp = await http.get(meta_url, headers=headers)
    if meta_resp.status_code >= 400:
        logger.error(
            "Graph API media metadata error: %s %s",
            meta_resp.status_code,
            meta_resp.text[:500],
        )
        return None
    try:
        meta = meta_resp.json()
    except json.JSONDecodeError:
        logger.error("Graph API media metadata: invalid JSON")
        return None
    download_url = meta.get("url")
    if not download_url or not isinstance(download_url, str):
        logger.error("Graph API media metadata: missing url")
        return None
    mime_type = meta.get("mime_type")
    mime_str = str(mime_type) if mime_type else None
    bin_resp = await http.get(download_url, headers=headers)
    if bin_resp.status_code >= 400:
        logger.error(
            "Graph API media download error: %s %s",
            bin_resp.status_code,
            bin_resp.text[:500],
        )
        return None
    return (bin_resp.content, mime_str)


def _buttons_to_graph_action(payload: InteractiveButtonsPayload) -> dict[str, Any]:
    return {
        "buttons": [
            {"type": "reply", "reply": {"id": b.id, "title": b.title}}
            for b in payload.buttons
        ]
    }


def _list_to_graph_action(payload: InteractiveListPayload) -> dict[str, Any]:
    sections_out: list[dict[str, Any]] = []
    for sec in payload.sections:
        row_objs: list[dict[str, Any]] = []
        for row in sec.rows:
            r: dict[str, Any] = {"id": row.id, "title": row.title}
            if row.description:
                r["description"] = row.description
            row_objs.append(r)
        sections_out.append(
            {
                "title": sec.title if sec.title else " ",
                "rows": row_objs,
            }
        )
    return {
        "button": payload.button_label,
        "sections": sections_out,
    }


async def send_interactive_buttons_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    payload: InteractiveButtonsPayload,
) -> bool:
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot send reply")
        return False
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    graph_payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": payload.body_text},
            "action": _buttons_to_graph_action(payload),
        },
    }
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    resp = await http.post(url, json=graph_payload, headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "Graph API error (interactive): %s %s",
            resp.status_code,
            resp.text[:500],
        )
        return False
    return True


async def send_interactive_list_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    payload: InteractiveListPayload,
) -> bool:
    """Send a list message (tap the button to open the list sheet — dropdown-style)."""
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot send reply")
        return False
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    graph_payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": payload.body_text},
            "action": _list_to_graph_action(payload),
        },
    }
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    resp = await http.post(url, json=graph_payload, headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "Graph API error (interactive list): %s %s",
            resp.status_code,
            resp.text[:500],
        )
        return False
    return True

import logging
from typing import Any

import httpx

from app.config import GRAPH_API_VERSION, WHATSAPP_ACCESS_TOKEN

logger = logging.getLogger(__name__)


async def send_text_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    body: str,
) -> None:
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot send reply")
        return
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


async def send_interactive_buttons_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    body_text: str = "Tap a button - demo reply.",
) -> None:
    if not WHATSAPP_ACCESS_TOKEN:
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
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    resp = await http.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "Graph API error (interactive): %s %s",
            resp.status_code,
            resp.text[:500],
        )


async def send_interactive_list_reply(
    http: httpx.AsyncClient,
    phone_number_id: str,
    to_wa_id: str,
    body_text: str = "Open the list and pick one option.",
) -> bool:
    """Send a list message (tap the button to open the list sheet — dropdown-style)."""
    if not WHATSAPP_ACCESS_TOKEN:
        logger.error("WHATSAPP_ACCESS_TOKEN is not set; cannot send reply")
        return False
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": "Choose option",
                "sections": [
                    {
                        "title": "Topics",
                        "rows": [
                            {
                                "id": "list_billing",
                                "title": "Billing",
                                "description": "Invoices and payments",
                            },
                            {
                                "id": "list_support",
                                "title": "Support",
                                "description": "Help with the product",
                            },
                            {
                                "id": "list_feedback",
                                "title": "Feedback",
                                "description": "Ideas and issues",
                            },
                        ],
                    },
                    {
                        "title": "Priority",
                        "rows": [
                            {
                                "id": "list_urgent",
                                "title": "Urgent",
                                "description": "Needs a fast reply",
                            },
                            {
                                "id": "list_normal",
                                "title": "Normal",
                                "description": "Whenever you can",
                            },
                        ],
                    },
                ],
            },
        },
    }
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    resp = await http.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "Graph API error (interactive list): %s %s",
            resp.status_code,
            resp.text[:500],
        )
        return False
    return True

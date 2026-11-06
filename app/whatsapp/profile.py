"""Keep the WhatsApp business profile (About / Description / Website) in sync on startup."""

from __future__ import annotations

import logging

import httpx

from app.config import GRAPH_API_VERSION, RENDER_EXTERNAL_URL, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID

logger = logging.getLogger(__name__)

# WhatsApp limits: about <= 139 chars, description <= 512 chars, websites <= 2.
ABOUT = "Design guidelines assistant. Tap the website link first to wake the bot, then message."
DESCRIPTION = (
    "Brand & design guidelines assistant: logos, colors, typography and moodboards.\n"
    "Test number: the bot sleeps when idle. Open the website link on this profile first "
    "(wait for 'ok'), then send your message."
)


async def sync_business_profile(http: httpx.AsyncClient) -> bool:
    if not (WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID and RENDER_EXTERNAL_URL):
        logger.info("Business profile sync skipped (missing token, phone number id or public URL)")
        return False
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/whatsapp_business_profile"
    payload = {
        "messaging_product": "whatsapp",
        "about": ABOUT[:139],
        "description": DESCRIPTION[:512],
        "websites": [f"{RENDER_EXTERNAL_URL.rstrip('/')}/wake"],
    }
    try:
        resp = await http.post(url, json=payload, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"})
    except httpx.HTTPError:
        logger.exception("Business profile sync failed")
        return False
    if resp.status_code >= 400:
        logger.error("Business profile sync error: %s %s", resp.status_code, resp.text[:500])
        return False
    logger.info("Business profile synced")
    return True

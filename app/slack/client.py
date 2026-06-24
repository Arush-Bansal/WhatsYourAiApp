import json
import logging
from typing import Any

import httpx

from app.config import SLACK_BOT_TOKEN
from app.slack.payloads import (
    InteractiveButtonsPayload,
    InteractiveMenuPayload,
    buttons_to_blocks,
    menu_to_blocks,
)

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}


async def send_text_reply(
    http: httpx.AsyncClient,
    channel_id: str,
    body: str,
) -> bool:
    if not SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN is not set; cannot send reply")
        return False
    payload = {"channel": channel_id, "text": body}
    resp = await http.post(
        f"{SLACK_API_BASE}/chat.postMessage",
        json=payload,
        headers=_auth_headers(),
    )
    if resp.status_code >= 400:
        logger.error("Slack API error: %s %s", resp.status_code, resp.text[:500])
        return False
    try:
        data = resp.json()
    except json.JSONDecodeError:
        logger.error("Slack chat.postMessage: invalid JSON")
        return False
    if not data.get("ok"):
        logger.error("Slack chat.postMessage failed: %s", data.get("error"))
        return False
    return True


async def send_blocks_reply(
    http: httpx.AsyncClient,
    channel_id: str,
    blocks: list[dict[str, Any]],
    *,
    fallback_text: str,
) -> bool:
    if not SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN is not set; cannot send reply")
        return False
    payload = {
        "channel": channel_id,
        "text": fallback_text,
        "blocks": blocks,
    }
    resp = await http.post(
        f"{SLACK_API_BASE}/chat.postMessage",
        json=payload,
        headers=_auth_headers(),
    )
    if resp.status_code >= 400:
        logger.error("Slack API error (blocks): %s %s", resp.status_code, resp.text[:500])
        return False
    try:
        data = resp.json()
    except json.JSONDecodeError:
        logger.error("Slack chat.postMessage (blocks): invalid JSON")
        return False
    if not data.get("ok"):
        logger.error("Slack chat.postMessage (blocks) failed: %s", data.get("error"))
        return False
    return True


async def send_interactive_buttons_reply(
    http: httpx.AsyncClient,
    channel_id: str,
    payload: InteractiveButtonsPayload,
) -> bool:
    blocks = buttons_to_blocks(payload)
    return await send_blocks_reply(
        http,
        channel_id,
        blocks,
        fallback_text=payload.body_text,
    )


async def send_interactive_menu_reply(
    http: httpx.AsyncClient,
    channel_id: str,
    payload: InteractiveMenuPayload,
) -> bool:
    blocks = menu_to_blocks(payload)
    return await send_blocks_reply(
        http,
        channel_id,
        blocks,
        fallback_text=payload.body_text,
    )


async def download_slack_file(
    http: httpx.AsyncClient,
    file_id: str,
) -> tuple[bytes, str | None] | None:
    """Resolve file_id via files.info and download bytes. Returns (body, mime_type) or None."""
    if not SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN is not set; cannot download file")
        return None
    headers = _auth_headers()
    info_resp = await http.get(
        f"{SLACK_API_BASE}/files.info",
        params={"file": file_id},
        headers=headers,
    )
    if info_resp.status_code >= 400:
        logger.error(
            "Slack files.info error: %s %s",
            info_resp.status_code,
            info_resp.text[:500],
        )
        return None
    try:
        info = info_resp.json()
    except json.JSONDecodeError:
        logger.error("Slack files.info: invalid JSON")
        return None
    if not info.get("ok"):
        logger.error("Slack files.info failed: %s", info.get("error"))
        return None
    file_obj = info.get("file") or {}
    download_url = file_obj.get("url_private_download") or file_obj.get("url_private")
    if not download_url or not isinstance(download_url, str):
        logger.error("Slack files.info: missing url_private")
        return None
    mime_type = file_obj.get("mimetype")
    mime_str = str(mime_type) if mime_type else None
    bin_resp = await http.get(download_url, headers=headers)
    if bin_resp.status_code >= 400:
        logger.error(
            "Slack file download error: %s %s",
            bin_resp.status_code,
            bin_resp.text[:500],
        )
        return None
    return (bin_resp.content, mime_str)

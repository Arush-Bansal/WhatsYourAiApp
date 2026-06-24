from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import GMAIL_MAILBOX_EMAIL, GMAIL_PUBSUB_TOPIC
from app.gmail.auth import get_access_token
from app.gmail.payloads import GmailReplyPayload, build_reply_raw

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _auth_headers() -> dict[str, str] | None:
    token = get_access_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


async def register_watch(http: httpx.AsyncClient) -> dict[str, Any] | None:
    """Register Gmail push notifications via Pub/Sub. Returns watch response or None."""
    headers = _auth_headers()
    if headers is None:
        return None
    if not GMAIL_PUBSUB_TOPIC:
        logger.error("GMAIL_PUBSUB_TOPIC is not set; cannot register watch")
        return None

    payload = {
        "topicName": GMAIL_PUBSUB_TOPIC,
        "labelIds": ["INBOX"],
        "labelFilterBehavior": "include",
    }
    resp = await http.post(
        f"{GMAIL_API_BASE}/watch",
        json=payload,
        headers=headers,
    )
    if resp.status_code >= 400:
        logger.error("Gmail watch error: %s %s", resp.status_code, resp.text[:500])
        return None
    try:
        return resp.json()
    except ValueError:
        logger.error("Gmail watch: invalid JSON response")
        return None


async def list_history(
    http: httpx.AsyncClient,
    start_history_id: str,
) -> dict[str, Any] | None:
    headers = _auth_headers()
    if headers is None:
        return None

    params: dict[str, str | list[str]] = {
        "startHistoryId": start_history_id,
        "historyTypes": "messageAdded",
    }
    resp = await http.get(
        f"{GMAIL_API_BASE}/history",
        params=params,
        headers=headers,
    )
    if resp.status_code == 404:
        logger.warning(
            "Gmail history.list 404 for startHistoryId=%s; history may be stale",
            start_history_id,
        )
        return None
    if resp.status_code >= 400:
        logger.error("Gmail history.list error: %s %s", resp.status_code, resp.text[:500])
        return None
    try:
        return resp.json()
    except ValueError:
        logger.error("Gmail history.list: invalid JSON response")
        return None


async def get_message(
    http: httpx.AsyncClient,
    message_id: str,
) -> dict[str, Any] | None:
    headers = _auth_headers()
    if headers is None:
        return None

    resp = await http.get(
        f"{GMAIL_API_BASE}/messages/{message_id}",
        params={"format": "full"},
        headers=headers,
    )
    if resp.status_code >= 400:
        logger.error(
            "Gmail messages.get error for %s: %s %s",
            message_id,
            resp.status_code,
            resp.text[:500],
        )
        return None
    try:
        return resp.json()
    except ValueError:
        logger.error("Gmail messages.get: invalid JSON response")
        return None


async def send_reply(
    http: httpx.AsyncClient,
    *,
    to_email: str,
    thread_id: str,
    subject: str,
    in_reply_to: str,
    references: str,
    payload: GmailReplyPayload,
) -> bool:
    headers = _auth_headers()
    if headers is None:
        return False

    mailbox = GMAIL_MAILBOX_EMAIL or "me"
    raw = build_reply_raw(
        to_email=to_email,
        from_email=mailbox,
        subject=subject,
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=references,
        payload=payload,
    )
    body = {"raw": raw, "threadId": thread_id}
    resp = await http.post(
        f"{GMAIL_API_BASE}/messages/send",
        json=body,
        headers=headers,
    )
    if resp.status_code >= 400:
        logger.error("Gmail messages.send error: %s %s", resp.status_code, resp.text[:500])
        return False
    return True


async def get_profile_history_id(http: httpx.AsyncClient) -> str | None:
    headers = _auth_headers()
    if headers is None:
        return None

    resp = await http.get(f"{GMAIL_API_BASE}/profile", headers=headers)
    if resp.status_code >= 400:
        logger.error("Gmail profile error: %s %s", resp.status_code, resp.text[:500])
        return None
    try:
        data = resp.json()
    except ValueError:
        logger.error("Gmail profile: invalid JSON response")
        return None
    history_id = data.get("historyId")
    return str(history_id) if history_id else None


async def mark_as_read(http: httpx.AsyncClient, message_id: str) -> bool:
    headers = _auth_headers()
    if headers is None:
        return False

    resp = await http.post(
        f"{GMAIL_API_BASE}/messages/{message_id}/modify",
        json={"removeLabelIds": ["UNREAD"]},
        headers=headers,
    )
    if resp.status_code >= 400:
        logger.error(
            "Gmail messages.modify error for %s: %s %s",
            message_id,
            resp.status_code,
            resp.text[:500],
        )
        return False
    return True

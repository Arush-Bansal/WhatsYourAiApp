from __future__ import annotations

import base64
import re
from html import unescape
from typing import Any, Iterator

from app.gmail.payloads import extract_email_address

_TAG_RE = re.compile(r"<[^>]+>")


def _header_map(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    out: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, dict):
            continue
        name = str(header.get("name") or "")
        value = str(header.get("value") or "")
        if name:
            out[name.lower()] = value
    return out


def _decode_body(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return raw.decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_body_from_part(part: dict[str, Any]) -> tuple[str | None, str | None]:
    mime_type = str(part.get("mimeType") or "")
    body_obj = part.get("body") or {}
    data = body_obj.get("data")
    if not data or not isinstance(data, str):
        return None, None
    decoded = _decode_body(data)
    if mime_type == "text/plain":
        return decoded, None
    if mime_type == "text/html":
        return None, decoded
    return None, None


def _walk_parts(part: dict[str, Any]) -> tuple[str | None, str | None]:
    plain: str | None = None
    html: str | None = None

    p_plain, p_html = _extract_body_from_part(part)
    if p_plain:
        plain = p_plain
    if p_html:
        html = p_html

    for child in part.get("parts") or []:
        if not isinstance(child, dict):
            continue
        c_plain, c_html = _walk_parts(child)
        if c_plain and not plain:
            plain = c_plain
        if c_html and not html:
            html = c_html

    return plain, html


def extract_body_plain(message: dict[str, Any]) -> str:
    payload = message.get("payload") or {}
    plain, html = _walk_parts(payload)
    if plain:
        return plain.strip()
    if html:
        return _strip_html(html)
    return ""


def message_has_label(message: dict[str, Any], label: str) -> bool:
    labels = message.get("labelIds") or []
    return label.upper() in {str(item).upper() for item in labels}


def parse_incoming_message(
    message: dict[str, Any],
    *,
    mailbox_email: str,
) -> tuple[str, str, str, str, str, str, str] | None:
    """
    Parse a Gmail API message into routing fields.

    Returns (message_id, thread_id, from_email, to_email, subject, body_plain,
    message_id_header) or None if the message should be skipped.
    """
    message_id = str(message.get("id") or "")
    thread_id = str(message.get("threadId") or "")
    if not message_id or not thread_id:
        return None

    if not message_has_label(message, "INBOX"):
        return None

    headers = _header_map(message)
    from_raw = headers.get("from", "")
    from_email = extract_email_address(from_raw)
    if not from_email:
        return None

    mailbox = mailbox_email.lower()
    if from_email == mailbox:
        return None

    subject = headers.get("subject", "")
    body_plain = extract_body_plain(message)
    message_id_header = headers.get("message-id", "")
    to_email = extract_email_address(headers.get("to", ""))

    return (
        message_id,
        thread_id,
        from_email,
        to_email,
        subject,
        body_plain,
        message_id_header,
    )


def iter_history_message_ids(history_response: dict[str, Any]) -> Iterator[str]:
    """Yield Gmail message IDs from a history.list response."""
    for record in history_response.get("history") or []:
        if not isinstance(record, dict):
            continue
        for added in record.get("messagesAdded") or []:
            if not isinstance(added, dict):
                continue
            msg = added.get("message") or {}
            if not isinstance(msg, dict):
                continue
            message_id = str(msg.get("id") or "")
            if message_id:
                yield message_id

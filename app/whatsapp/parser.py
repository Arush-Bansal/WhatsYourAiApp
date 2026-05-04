from typing import Any

from app.config import WHATSAPP_PHONE_NUMBER_ID


def iter_incoming_text_messages(
    data: dict[str, Any],
) -> list[tuple[str, str, str, str]]:
    """Return list of (message_id, from_wa_id, text_body, phone_number_id)."""
    out: list[tuple[str, str, str, str]] = []
    if data.get("object") != "whatsapp_business_account":
        return out
    for entry in data.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(
                metadata.get("phone_number_id") or WHATSAPP_PHONE_NUMBER_ID or ""
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


def iter_incoming_button_replies(
    data: dict[str, Any],
) -> list[tuple[str, str, str, str, str]]:
    """Return list of (message_id, from_wa_id, button_id, button_title, phone_number_id)
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
                metadata.get("phone_number_id") or WHATSAPP_PHONE_NUMBER_ID or ""
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

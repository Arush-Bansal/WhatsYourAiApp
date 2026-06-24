from typing import Any


def _is_bot_message(event: dict[str, Any]) -> bool:
    if event.get("bot_id"):
        return True
    if event.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
        return True
    return False


def iter_incoming_dm_text(
    data: dict[str, Any],
) -> list[tuple[str, str, str, str]]:
    """Return list of (event_id, channel_id, user_id, text_body) for DM text messages."""
    out: list[tuple[str, str, str, str]] = []
    if data.get("type") != "event_callback":
        return out
    event = data.get("event") or {}
    if event.get("type") != "message":
        return out
    if event.get("channel_type") != "im":
        return out
    if _is_bot_message(event):
        return out
    if event.get("files"):
        return out
    text = event.get("text")
    if text is None:
        return out
    event_id = str(data.get("event_id") or "")
    channel_id = str(event.get("channel") or "")
    user_id = str(event.get("user") or "")
    if event_id and channel_id and user_id:
        out.append((event_id, channel_id, user_id, str(text)))
    return out


def iter_incoming_audio_files(
    data: dict[str, Any],
) -> list[tuple[str, str, str, str]]:
    """Return list of (event_id, channel_id, user_id, file_id) for DM audio attachments."""
    out: list[tuple[str, str, str, str]] = []
    if data.get("type") != "event_callback":
        return out
    event = data.get("event") or {}
    if event.get("type") != "message":
        return out
    if event.get("channel_type") != "im":
        return out
    if _is_bot_message(event):
        return out
    files = event.get("files") or []
    if not files:
        return out
    event_id = str(data.get("event_id") or "")
    channel_id = str(event.get("channel") or "")
    user_id = str(event.get("user") or "")
    if not (event_id and channel_id and user_id):
        return out
    for file_obj in files:
        if not isinstance(file_obj, dict):
            continue
        mimetype = str(file_obj.get("mimetype") or "")
        if not mimetype.startswith("audio/"):
            continue
        file_id = str(file_obj.get("id") or "")
        if file_id:
            out.append((event_id, channel_id, user_id, file_id))
    return out


def _parse_interactivity_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    if data.get("type") != "block_actions":
        return None
    return data


def iter_button_actions(
    data: dict[str, Any],
) -> list[tuple[str, str, str, str, str, str]]:
    """Return (dedupe_id, channel_id, user_id, action_id, button_text, value)."""
    out: list[tuple[str, str, str, str, str, str]] = []
    payload = _parse_interactivity_payload(data)
    if payload is None:
        return out
    channel_id = str((payload.get("channel") or {}).get("id") or "")
    user_id = str((payload.get("user") or {}).get("id") or "")
    dedupe_id = str(payload.get("trigger_id") or payload.get("response_url") or "")
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        if action.get("type") != "button":
            continue
        action_id = str(action.get("action_id") or "")
        button_text = str((action.get("text") or {}).get("text") or action_id)
        value = str(action.get("value") or "")
        if dedupe_id and channel_id and user_id and action_id:
            out.append((dedupe_id, channel_id, user_id, action_id, button_text, value))
    return out


def iter_select_actions(
    data: dict[str, Any],
) -> list[tuple[str, str, str, str, str, str]]:
    """Return (dedupe_id, channel_id, user_id, action_id, option_value, option_text)."""
    out: list[tuple[str, str, str, str, str, str]] = []
    payload = _parse_interactivity_payload(data)
    if payload is None:
        return out
    channel_id = str((payload.get("channel") or {}).get("id") or "")
    user_id = str((payload.get("user") or {}).get("id") or "")
    dedupe_id = str(payload.get("trigger_id") or payload.get("response_url") or "")
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        if action.get("type") != "static_select":
            continue
        action_id = str(action.get("action_id") or "")
        selected = action.get("selected_option") or {}
        option_value = str(selected.get("value") or "")
        option_text = str((selected.get("text") or {}).get("text") or option_value)
        if dedupe_id and channel_id and user_id and action_id and option_value:
            out.append(
                (dedupe_id, channel_id, user_id, action_id, option_value, option_text)
            )
    return out

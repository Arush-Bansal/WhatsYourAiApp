from app.config import PROCESSED_IDS_MAX

_processed_message_ids: set[str] = set()


def already_processed(message_id: str) -> bool:
    return message_id in _processed_message_ids


def mark_processed(message_id: str) -> None:
    _processed_message_ids.add(message_id)
    if len(_processed_message_ids) > PROCESSED_IDS_MAX:
        _processed_message_ids.clear()

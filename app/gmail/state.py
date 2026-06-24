from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import GMAIL_STATE_PATH

logger = logging.getLogger(__name__)


def _state_file() -> Path:
    return Path(GMAIL_STATE_PATH)


def load_last_history_id() -> str | None:
    path = _state_file()
    if not path.is_file():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Gmail state file %s: %s", path, exc)
        return None
    history_id = data.get("last_history_id")
    return str(history_id) if history_id else None


def save_last_history_id(history_id: str) -> None:
    path = _state_file()
    payload = {"last_history_id": history_id}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.error("Could not write Gmail state file %s: %s", path, exc)

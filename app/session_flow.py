"""Deterministic session commands (new/wrap) so the LLM is not required for them."""

from __future__ import annotations

from app.memory import wrap_current_session
from app.store import Store

NEW_SESSION_WORDS = {"new session", "start session", "start over", "fresh session"}
WRAP_WORDS = {"wrap up", "end session", "close session", "that's all", "thats all"}


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def is_new_session_command(text: str) -> bool:
    return _norm(text) in NEW_SESSION_WORDS


def is_wrap_command(text: str) -> bool:
    return _norm(text) in WRAP_WORDS


async def wrap_up(store: Store, wa_id: str) -> str:
    await wrap_current_session(store, wa_id)
    return "Wrapped this session. Next message starts a new one — I'll keep the brand card."


async def start_new(store: Store, wa_id: str) -> str:
    await wrap_current_session(store, wa_id)
    brand = await store.active_brand(wa_id)
    await store.force_new_session(wa_id, brand.id)
    return "New session. What are we working on?"

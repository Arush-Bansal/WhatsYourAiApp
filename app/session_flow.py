"""Deterministic session commands (new/wrap) so the LLM is not required for them."""

from __future__ import annotations

import difflib
import re

from app.memory import wrap_current_session
from app.store import Store

NEW_SESSION_WORDS = {"new session", "start session", "start over", "fresh session"}
WRAP_WORDS = {"wrap up", "end session", "close session", "that's all", "thats all"}


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


_SESSION_NOUNS = ["session", "chat", "conversation"]


def _is_session_word(word: str) -> bool:
    return bool(difflib.get_close_matches(word, _SESSION_NOUNS, n=1, cutoff=0.75))


def is_new_session_command(text: str) -> bool:
    """Exact commands, or a short message like 'heey new sessoin please' (typos tolerated;
    long messages are never commands)."""
    t = _norm(text)
    if t in NEW_SESSION_WORDS:
        return True
    if len(t) > 40:
        return False
    if re.search(r"\b(start (over|again)|fresh start)\b", t):
        return True
    words = re.findall(r"[a-z]+", t)
    return any(w == "new" and i + 1 < len(words) and _is_session_word(words[i + 1]) for i, w in enumerate(words))


def is_wrap_command(text: str) -> bool:
    return _norm(text) in WRAP_WORDS


async def wrap_up(store: Store, wa_id: str) -> str:
    await store.clear_form_session(wa_id)
    await wrap_current_session(store, wa_id)
    return "Wrapped this session. Next message starts a new one — I'll keep the brand card."


async def start_new(store: Store, wa_id: str) -> str:
    await store.clear_form_session(wa_id)
    await wrap_current_session(store, wa_id)
    brand = await store.active_brand(wa_id)
    await store.force_new_session(wa_id, brand.id)
    return "New session. What are we working on?"

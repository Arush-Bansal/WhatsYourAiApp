"""Context management: brand card + session summaries + a token-bounded recent window."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_SUMMARY_MODEL
from app.store import Brand, ChatSession, Msg, Store

logger = logging.getLogger(__name__)

# Token budgets (rough estimate: 1 token ~ 4 characters).
RECENT_BUDGET = 1800  # recent messages replayed verbatim
COMPACT_AT = 3200  # in-session history size that triggers folding the older part into the summary
KEEP_RECENT = 1200  # tokens of the newest messages left verbatim after folding
PAST_SESSIONS = 3  # closed-session summaries of the active brand shown to the model
MAX_SUMMARY_CHARS = 1200

CARD_FIELDS: dict[str, str] = {
    "category": "what it sells and the category buyers compare it in",
    "audience": "who it is for and when they meet the brand",
    "difference": "the one win over the usual alternative",
    "touchpoints": "where the brand shows up most",
    "personality": "3 words for how it should feel",
    "avoid": "what it must not look like",
    "style": "preferred logo style / mark type",
    "colors": "palette decisions (roles and hex)",
    "fonts": "type decisions",
    "tagline": "tagline or descriptor",
    "logo_notes": "decisions about the logo",
    "preferences": "lasting likes and dislikes",
    "locked": "things the user approved and wants kept",
}


def est_tokens(text: str) -> int:
    return len(text) // 4 + 4


@dataclass
class TurnContext:
    brand: Brand
    session: ChatSession
    memory_block: str  # brand card + summaries, as a system message
    history: list[dict[str, str]]  # recent messages, oldest first


def render_card(brand: Brand) -> str:
    lines = [f"Active brand: {brand.name}"]
    lines += [f"- {k}: {v}" for k, v in brand.card.items() if v]
    if len(lines) == 1:
        lines.append("(nothing saved yet)")
    return "\n".join(lines)


def render_session(session: ChatSession) -> str:
    lines = [f"This session: mode={session.mode}"]
    if session.goal:
        lines.append(f"Goal: {session.goal}")
    if session.plan:
        lines.append("Agreed flow:")
        lines += [f"{i}. {p}" for i, p in enumerate(session.plan, 1)]
    return "\n".join(lines)


def build_memory_block(
    brand: Brand,
    brands: list[Brand],
    session_summary: str,
    past: list[str],
    session: ChatSession | None = None,
) -> str:
    parts = ["Saved memory (trust it; do not re-ask what is here):", render_card(brand)]
    others = [b.name for b in brands if b.id != brand.id]
    if others:
        parts.append("Other brands this user has: " + ", ".join(others))
    if past:
        parts.append("Earlier sessions on this brand:\n" + "\n".join(f"- {s}" for s in past))
    if session is not None and (session.goal or session.plan or session.mode != "explore"):
        parts.append(render_session(session))
    if session_summary:
        parts.append("Earlier in this session:\n" + session_summary)
    return "\n\n".join(parts)


def pick_recent(messages: list[Msg], budget: int) -> list[Msg]:
    """Newest messages that fit the token budget, oldest first."""
    chosen: list[Msg] = []
    used = 0
    for m in reversed(messages):
        cost = est_tokens(m.content)
        if chosen and used + cost > budget:
            break
        chosen.append(m)
        used += cost
    return list(reversed(chosen))


def _transcript(messages: list[Msg]) -> str:
    return "\n".join(f"{'User' if m.role == 'user' else 'Assistant'}: {m.content[:600]}" for m in messages)


async def summarise(
    prev_summary: str, messages: list[Msg], card: dict[str, str]
) -> tuple[str, dict[str, str]]:
    """One cheap call: fold messages into the summary AND extract durable brand facts for the card."""
    fallback = (prev_summary + " " + _transcript(messages)[:500]).strip()[:MAX_SUMMARY_CHARS]
    key = (OPENAI_API_KEY or "").strip()
    if not key:
        return fallback, {}
    system = (
        "You maintain memory for a brand-design assistant. Given the previous summary and new messages, return JSON "
        '{"summary": "...", "card": {...}}. summary: <=120 words, what was discussed, decided and still open; '
        "no pleasantries. card: only NEW or CHANGED durable brand facts the user actually stated or approved, "
        "using only these keys: " + ", ".join(CARD_FIELDS) + ". Short phrases. Never invent. Omit keys with nothing new."
    )
    user = f"Current card: {json.dumps(card)}\nPrevious summary: {prev_summary or '(none)'}\nNew messages:\n{_transcript(messages)}"
    try:
        client = AsyncOpenAI(api_key=key, timeout=60.0)
        resp = await client.chat.completions.create(
            model=OPENAI_SUMMARY_MODEL,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        summary = str(data.get("summary") or fallback)[:MAX_SUMMARY_CHARS]
        raw = data.get("card") if isinstance(data.get("card"), dict) else {}
        patch = {k: str(v) for k, v in raw.items() if k in CARD_FIELDS and v}
        return summary, patch
    except Exception:
        logger.exception("Summarisation failed; using fallback")
        return fallback, {}


async def prepare_turn(store: Store, wa_id: str) -> TurnContext:
    brand = await store.active_brand(wa_id)
    session = await store.open_session(wa_id, brand.id)

    # Close out earlier sessions: summarise them and fold lasting facts into their brand's card.
    for old in await store.unsummarised_sessions(wa_id, session.id):
        msgs = [m for m in await store.session_messages(old.id)]
        if len(msgs) >= 2:
            summary, patch = await summarise(old.summary, [m for m in msgs if not m.compacted], {})
            if patch:
                await store.update_brand(old.brand_id, None, patch)
                if old.brand_id == brand.id:
                    brand = (await _fresh(store, wa_id, brand.id)) or brand
            await store.set_session_summary(old.id, summary, closed=True)
        else:
            await store.set_session_summary(old.id, "", closed=True)

    msgs = [m for m in await store.session_messages(session.id) if not m.compacted]

    # Fold the older part of a long session into its rolling summary ("memory flush" into the card first).
    if sum(est_tokens(m.content) for m in msgs) > COMPACT_AT:
        keep = pick_recent(msgs, KEEP_RECENT)
        old_part = msgs[: len(msgs) - len(keep)]
        if old_part:
            summary, patch = await summarise(session.summary, old_part, brand.card)
            if patch:
                brand = await store.update_brand(brand.id, None, patch)
            await store.set_session_summary(session.id, summary, compact_upto=old_part[-1].id)
            session.summary = summary
            msgs = keep

    recent = pick_recent(msgs, RECENT_BUDGET)
    past = await store.brand_summaries(brand.id, session.id, PAST_SESSIONS)
    block = build_memory_block(brand, await store.list_brands(wa_id), session.summary, past, session)
    return TurnContext(brand, session, block, [{"role": m.role, "content": m.content} for m in recent])


async def wrap_current_session(store: Store, wa_id: str) -> ChatSession | None:
    """Summarise and close the open session so the next turn is a new one.

    Does not create a session if none is open.
    """
    open_list = await store.unsummarised_sessions(wa_id, exclude_id=0)
    if not open_list:
        return None
    session = max(open_list, key=lambda s: s.id)
    brand = await store.active_brand(wa_id)
    msgs = [m for m in await store.session_messages(session.id) if not m.compacted]
    if len(msgs) >= 2:
        card = brand.card if brand.id == session.brand_id else {}
        summary, patch = await summarise(session.summary, msgs, card)
        if patch:
            await store.update_brand(session.brand_id, None, patch)
        await store.set_session_summary(session.id, summary, closed=True)
    elif not session.summarised:
        await store.set_session_summary(session.id, session.summary, closed=True)
    return session


async def _fresh(store: Store, wa_id: str, brand_id: int) -> Brand | None:
    return next((b for b in await store.list_brands(wa_id) if b.id == brand_id), None)

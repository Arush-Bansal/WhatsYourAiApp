"""Persistent state for the bot: Postgres (Supabase) when DATABASE_URL is set, else in-memory."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import asyncpg

from app.config import DATABASE_URL, PROCESSED_IDS_MAX

logger = logging.getLogger(__name__)

FORM_SESSION_TTL = timedelta(hours=24)
SESSION_GAP = timedelta(minutes=30)  # a longer silence starts a new chat session
DEFAULT_BRAND_NAME = "My brand"


@dataclass
class FormSession:
    wa_id: str
    form_id: str
    step: int = 0
    answers: dict[str, str] = field(default_factory=dict)


@dataclass
class Brand:
    id: int
    wa_id: str
    name: str
    card: dict[str, str] = field(default_factory=dict)


@dataclass
class ChatSession:
    id: int
    wa_id: str
    brand_id: int
    summary: str = ""
    summarised: bool = False


@dataclass
class Msg:
    id: int
    role: str
    content: str
    compacted: bool = False


class Store(Protocol):
    async def claim_message(self, message_id: str) -> bool:
        """Atomically record message_id; False if it was already seen."""

    async def get_form_session(self, wa_id: str) -> FormSession | None: ...
    async def save_form_session(self, session: FormSession) -> None: ...
    async def clear_form_session(self, wa_id: str) -> None: ...
    async def save_submission(self, wa_id: str, form_id: str, answers: dict[str, str]) -> None: ...

    # brands: one card of durable facts per brand; one brand is active per user
    async def active_brand(self, wa_id: str) -> Brand: ...
    async def create_brand(self, wa_id: str, name: str) -> Brand: ...
    async def switch_brand(self, wa_id: str, name: str) -> Brand | None: ...
    async def list_brands(self, wa_id: str) -> list[Brand]: ...
    async def update_brand(self, brand_id: int, name: str | None, card_patch: dict[str, str]) -> Brand: ...

    # chat sessions and their messages
    async def open_session(self, wa_id: str, brand_id: int) -> ChatSession:
        """Current session (touching it), or a new one after SESSION_GAP of silence / a brand switch."""

    async def unsummarised_sessions(self, wa_id: str, exclude_id: int) -> list[ChatSession]: ...
    async def brand_summaries(self, brand_id: int, exclude_id: int, limit: int) -> list[str]: ...
    async def set_session_summary(
        self, session_id: int, summary: str, *, closed: bool = False, compact_upto: int | None = None
    ) -> None:
        """Store the summary; closed=True marks the session finished, compact_upto hides folded messages."""

    async def append_message(self, wa_id: str, role: str, content: str, session_id: int | None = None) -> None: ...
    async def session_messages(self, session_id: int) -> list[Msg]: ...

    async def close(self) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._forms: dict[str, tuple[FormSession, datetime]] = {}
        self.submissions: list[tuple[str, str, dict[str, str]]] = []
        self._brands: dict[int, Brand] = {}
        self._active: dict[str, int] = {}
        self._sessions: dict[int, tuple[ChatSession, datetime]] = {}
        self._msgs: dict[int, list[Msg]] = {}
        self._loose: list[tuple[str, str, str]] = []
        self._ids = 0

    def _next(self) -> int:
        self._ids += 1
        return self._ids

    async def claim_message(self, message_id: str) -> bool:
        if message_id in self._seen:
            return False
        self._seen.add(message_id)
        if len(self._seen) > PROCESSED_IDS_MAX:
            self._seen.clear()
        return True

    async def get_form_session(self, wa_id: str) -> FormSession | None:
        item = self._forms.get(wa_id)
        if item is None:
            return None
        session, updated = item
        if datetime.now(timezone.utc) - updated > FORM_SESSION_TTL:
            del self._forms[wa_id]
            return None
        return session

    async def save_form_session(self, session: FormSession) -> None:
        self._forms[session.wa_id] = (session, datetime.now(timezone.utc))

    async def clear_form_session(self, wa_id: str) -> None:
        self._forms.pop(wa_id, None)

    async def save_submission(self, wa_id: str, form_id: str, answers: dict[str, str]) -> None:
        self.submissions.append((wa_id, form_id, answers))

    async def active_brand(self, wa_id: str) -> Brand:
        bid = self._active.get(wa_id)
        if bid is not None:
            return self._brands[bid]
        return await self.create_brand(wa_id, DEFAULT_BRAND_NAME)

    async def create_brand(self, wa_id: str, name: str) -> Brand:
        brand = Brand(self._next(), wa_id, name.strip() or DEFAULT_BRAND_NAME)
        self._brands[brand.id] = brand
        self._active[wa_id] = brand.id
        return brand

    async def switch_brand(self, wa_id: str, name: str) -> Brand | None:
        brand = _match_brand(await self.list_brands(wa_id), name)
        if brand is not None:
            self._active[wa_id] = brand.id
        return brand

    async def list_brands(self, wa_id: str) -> list[Brand]:
        return [b for b in self._brands.values() if b.wa_id == wa_id]

    async def update_brand(self, brand_id: int, name: str | None, card_patch: dict[str, str]) -> Brand:
        brand = self._brands[brand_id]
        if name:
            brand.name = name
        _merge_card(brand.card, card_patch)
        return brand

    async def open_session(self, wa_id: str, brand_id: int) -> ChatSession:
        now = datetime.now(timezone.utc)
        mine = [(s, t) for s, t in self._sessions.values() if s.wa_id == wa_id]
        if mine:
            last, touched = max(mine, key=lambda x: x[0].id)
            if last.brand_id == brand_id and now - touched <= SESSION_GAP and not last.summarised:
                self._sessions[last.id] = (last, now)
                return last
        session = ChatSession(self._next(), wa_id, brand_id)
        self._sessions[session.id] = (session, now)
        return session

    async def unsummarised_sessions(self, wa_id: str, exclude_id: int) -> list[ChatSession]:
        return sorted(
            (s for s, _ in self._sessions.values() if s.wa_id == wa_id and s.id != exclude_id and not s.summarised),
            key=lambda s: s.id,
        )

    async def brand_summaries(self, brand_id: int, exclude_id: int, limit: int) -> list[str]:
        done = sorted(
            (s for s, _ in self._sessions.values() if s.brand_id == brand_id and s.id != exclude_id and s.summarised and s.summary),
            key=lambda s: s.id,
        )
        return [s.summary for s in done][-limit:]

    async def set_session_summary(
        self, session_id: int, summary: str, *, closed: bool = False, compact_upto: int | None = None
    ) -> None:
        session, touched = self._sessions[session_id]
        session.summary = summary
        if closed:
            session.summarised = True
        if compact_upto is not None:
            for m in self._msgs.get(session_id, []):
                if m.id <= compact_upto:
                    m.compacted = True

    async def append_message(self, wa_id: str, role: str, content: str, session_id: int | None = None) -> None:
        if session_id is None:
            self._loose.append((wa_id, role, content))
            return
        self._msgs.setdefault(session_id, []).append(Msg(self._next(), role, content))

    async def session_messages(self, session_id: int) -> list[Msg]:
        return list(self._msgs.get(session_id, []))

    async def close(self) -> None:
        return None


def _match_brand(brands: list[Brand], name: str) -> Brand | None:
    needle = name.strip().lower()
    for b in brands:
        if b.name.lower() == needle:
            return b
    for b in brands:
        if needle and needle in b.name.lower():
            return b
    return None


def _merge_card(card: dict[str, str], patch: dict[str, str]) -> None:
    """Set non-empty values; an empty string clears the field."""
    for key, value in patch.items():
        value = (value or "").strip()
        if value:
            card[key] = value
        else:
            card.pop(key, None)


def _brand_from_row(row: Any) -> Brand:
    card: Any = row["card"]
    if isinstance(card, str):
        card = json.loads(card)
    return Brand(row["id"], row["wa_id"], row["name"], dict(card))


class PgStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgStore":
        # statement_cache_size=0: Supabase's pooler may run in transaction mode.
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, statement_cache_size=0)
        return cls(pool)

    async def claim_message(self, message_id: str) -> bool:
        row = await self._pool.fetchrow(
            "insert into wa_agent.processed_messages (message_id) values ($1) "
            "on conflict do nothing returning message_id",
            message_id,
        )
        return row is not None

    async def get_form_session(self, wa_id: str) -> FormSession | None:
        row = await self._pool.fetchrow(
            "select form_id, step, answers, updated_at from wa_agent.form_sessions where wa_id = $1",
            wa_id,
        )
        if row is None:
            return None
        if datetime.now(timezone.utc) - row["updated_at"] > FORM_SESSION_TTL:
            await self.clear_form_session(wa_id)
            return None
        answers: Any = row["answers"]
        if isinstance(answers, str):
            answers = json.loads(answers)
        return FormSession(wa_id, row["form_id"], row["step"], dict(answers))

    async def save_form_session(self, session: FormSession) -> None:
        await self._pool.execute(
            "insert into wa_agent.form_sessions (wa_id, form_id, step, answers, updated_at) "
            "values ($1, $2, $3, $4::jsonb, now()) "
            "on conflict (wa_id) do update set form_id = excluded.form_id, step = excluded.step, "
            "answers = excluded.answers, updated_at = now()",
            session.wa_id,
            session.form_id,
            session.step,
            json.dumps(session.answers),
        )

    async def clear_form_session(self, wa_id: str) -> None:
        await self._pool.execute("delete from wa_agent.form_sessions where wa_id = $1", wa_id)

    async def save_submission(self, wa_id: str, form_id: str, answers: dict[str, str]) -> None:
        await self._pool.execute(
            "insert into wa_agent.form_submissions (wa_id, form_id, answers) values ($1, $2, $3::jsonb)",
            wa_id,
            form_id,
            json.dumps(answers),
        )

    async def active_brand(self, wa_id: str) -> Brand:
        row = await self._pool.fetchrow("select * from wa_agent.brands where wa_id = $1 and active", wa_id)
        if row is None:
            row = await self._pool.fetchrow(
                "update wa_agent.brands set active = true where id = ("
                "select id from wa_agent.brands where wa_id = $1 order by id desc limit 1) returning *",
                wa_id,
            )
        if row is None:
            return await self.create_brand(wa_id, DEFAULT_BRAND_NAME)
        return _brand_from_row(row)

    async def create_brand(self, wa_id: str, name: str) -> Brand:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("update wa_agent.brands set active = false where wa_id = $1 and active", wa_id)
            row = await conn.fetchrow(
                "insert into wa_agent.brands (wa_id, name, active) values ($1, $2, true) returning *",
                wa_id,
                name.strip() or DEFAULT_BRAND_NAME,
            )
        return _brand_from_row(row)

    async def switch_brand(self, wa_id: str, name: str) -> Brand | None:
        brand = _match_brand(await self.list_brands(wa_id), name)
        if brand is None:
            return None
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("update wa_agent.brands set active = false where wa_id = $1 and active", wa_id)
            await conn.execute("update wa_agent.brands set active = true where id = $1", brand.id)
        return brand

    async def list_brands(self, wa_id: str) -> list[Brand]:
        rows = await self._pool.fetch("select * from wa_agent.brands where wa_id = $1 order by id", wa_id)
        return [_brand_from_row(r) for r in rows]

    async def update_brand(self, brand_id: int, name: str | None, card_patch: dict[str, str]) -> Brand:
        row = await self._pool.fetchrow("select * from wa_agent.brands where id = $1", brand_id)
        brand = _brand_from_row(row)
        _merge_card(brand.card, card_patch)
        if name:
            brand.name = name
        await self._pool.execute(
            "update wa_agent.brands set name = $2, card = $3::jsonb, updated_at = now() where id = $1",
            brand_id,
            brand.name,
            json.dumps(brand.card),
        )
        return brand

    async def open_session(self, wa_id: str, brand_id: int) -> ChatSession:
        row = await self._pool.fetchrow(
            "update wa_agent.sessions set last_at = now() where id = ("
            "select id from wa_agent.sessions where wa_id = $1 and brand_id = $2 and not summarised "
            "and last_at > now() - make_interval(secs => $3) order by id desc limit 1) "
            "returning id, wa_id, brand_id, summary, summarised",
            wa_id,
            brand_id,
            SESSION_GAP.total_seconds(),
        )
        if row is None:
            row = await self._pool.fetchrow(
                "insert into wa_agent.sessions (wa_id, brand_id) values ($1, $2) "
                "returning id, wa_id, brand_id, summary, summarised",
                wa_id,
                brand_id,
            )
        return ChatSession(row["id"], row["wa_id"], row["brand_id"], row["summary"], row["summarised"])

    async def unsummarised_sessions(self, wa_id: str, exclude_id: int) -> list[ChatSession]:
        rows = await self._pool.fetch(
            "select id, wa_id, brand_id, summary, summarised from wa_agent.sessions "
            "where wa_id = $1 and id <> $2 and not summarised order by id limit 10",
            wa_id,
            exclude_id,
        )
        return [ChatSession(r["id"], r["wa_id"], r["brand_id"], r["summary"], r["summarised"]) for r in rows]

    async def brand_summaries(self, brand_id: int, exclude_id: int, limit: int) -> list[str]:
        rows = await self._pool.fetch(
            "select summary from wa_agent.sessions where brand_id = $1 and id <> $2 and summarised "
            "and summary <> '' order by id desc limit $3",
            brand_id,
            exclude_id,
            limit,
        )
        return [r["summary"] for r in reversed(rows)]

    async def set_session_summary(
        self, session_id: int, summary: str, *, closed: bool = False, compact_upto: int | None = None
    ) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "update wa_agent.sessions set summary = $2, summarised = summarised or $3 where id = $1",
                session_id,
                summary,
                closed,
            )
            if compact_upto is not None:
                await conn.execute(
                    "update wa_agent.messages set compacted = true where session_id = $1 and id <= $2",
                    session_id,
                    compact_upto,
                )

    async def append_message(self, wa_id: str, role: str, content: str, session_id: int | None = None) -> None:
        await self._pool.execute(
            "insert into wa_agent.messages (wa_id, role, content, session_id) values ($1, $2, $3, $4)",
            wa_id,
            role,
            content,
            session_id,
        )

    async def session_messages(self, session_id: int) -> list[Msg]:
        rows = await self._pool.fetch(
            "select id, role, content, compacted from wa_agent.messages where session_id = $1 order by id",
            session_id,
        )
        return [Msg(r["id"], r["role"], r["content"], r["compacted"]) for r in rows]

    async def close(self) -> None:
        await self._pool.close()


async def create_store() -> Store:
    if not DATABASE_URL:
        logger.warning("DATABASE_URL is not set; using in-memory store (state is lost on restart)")
        return MemoryStore()
    try:
        return await PgStore.connect(DATABASE_URL)
    except Exception:
        logger.exception("Could not connect to Postgres; falling back to in-memory store")
        return MemoryStore()

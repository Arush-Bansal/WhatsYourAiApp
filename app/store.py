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


@dataclass
class FormSession:
    wa_id: str
    form_id: str
    step: int = 0
    answers: dict[str, str] = field(default_factory=dict)


class Store(Protocol):
    async def claim_message(self, message_id: str) -> bool:
        """Atomically record message_id; False if it was already seen."""

    async def get_form_session(self, wa_id: str) -> FormSession | None: ...
    async def save_form_session(self, session: FormSession) -> None: ...
    async def clear_form_session(self, wa_id: str) -> None: ...
    async def save_submission(self, wa_id: str, form_id: str, answers: dict[str, str]) -> None: ...
    async def close(self) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._sessions: dict[str, tuple[FormSession, datetime]] = {}
        self.submissions: list[tuple[str, str, dict[str, str]]] = []

    async def claim_message(self, message_id: str) -> bool:
        if message_id in self._seen:
            return False
        self._seen.add(message_id)
        if len(self._seen) > PROCESSED_IDS_MAX:
            self._seen.clear()
        return True

    async def get_form_session(self, wa_id: str) -> FormSession | None:
        item = self._sessions.get(wa_id)
        if item is None:
            return None
        session, updated = item
        if datetime.now(timezone.utc) - updated > FORM_SESSION_TTL:
            del self._sessions[wa_id]
            return None
        return session

    async def save_form_session(self, session: FormSession) -> None:
        self._sessions[session.wa_id] = (session, datetime.now(timezone.utc))

    async def clear_form_session(self, wa_id: str) -> None:
        self._sessions.pop(wa_id, None)

    async def save_submission(self, wa_id: str, form_id: str, answers: dict[str, str]) -> None:
        self.submissions.append((wa_id, form_id, answers))

    async def close(self) -> None:
        return None


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

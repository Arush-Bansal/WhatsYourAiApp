"""Collect a burst of user messages and answer them with one agent turn."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TEXT_DELAY = 2.5  # wait for more messages after plain text / media
TAP_DELAY = 0.3  # button and list taps are deliberate single actions


@dataclass
class Item:
    text: str
    parts: list[dict[str, Any]] = field(default_factory=list)  # attachments as model input parts
    tap: bool = False
    message_id: str = ""  # WhatsApp message id, used for the typing indicator


Runner = Callable[[str, str, list[Item]], Awaitable[None]]  # (wa_id, phone_number_id, items)


class Batcher:
    def __init__(self, text_delay: float = TEXT_DELAY, tap_delay: float = TAP_DELAY) -> None:
        self._text_delay = text_delay
        self._tap_delay = tap_delay
        self._pending: dict[str, list[Item]] = {}
        self._gen: dict[str, int] = {}
        self._phone: dict[str, str] = {}
        self._runner: dict[str, Runner] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def lock(self, wa_id: str) -> asyncio.Lock:
        """Per-user lock: a user's form handling and agent turns never overlap."""
        return self._locks.setdefault(wa_id, asyncio.Lock())

    def add(self, wa_id: str, phone_number_id: str, item: Item, runner: Runner) -> None:
        self._pending.setdefault(wa_id, []).append(item)
        self._phone[wa_id] = phone_number_id
        self._runner[wa_id] = runner
        gen = self._gen[wa_id] = self._gen.get(wa_id, 0) + 1
        delay = self._tap_delay if item.tap else self._text_delay
        task = asyncio.create_task(self._flush(wa_id, gen, delay))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _flush(self, wa_id: str, gen: int, delay: float) -> None:
        await asyncio.sleep(delay)
        if self._gen.get(wa_id) != gen:
            return  # a newer message restarted the wait
        async with self.lock(wa_id):
            items = self._pending.pop(wa_id, [])
            if not items:
                return
            try:
                await self._runner[wa_id](wa_id, self._phone[wa_id], items)
            except Exception:
                logger.exception("Batched agent turn failed")


batcher = Batcher()

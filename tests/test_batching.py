import asyncio

import pytest

from app.batching import Batcher, Item


@pytest.mark.asyncio
async def test_burst_becomes_one_run():
    b = Batcher(text_delay=0.05, tap_delay=0.01)
    runs = []

    async def runner(wa, pn, items):
        runs.append([i.text for i in items])

    for t in ("a", "b", "c"):
        b.add("91", "pn", Item(t), runner)
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.2)
    assert runs == [["a", "b", "c"]]


@pytest.mark.asyncio
async def test_messages_during_a_run_form_the_next_batch():
    b = Batcher(text_delay=0.02, tap_delay=0.01)
    runs, gate = [], asyncio.Event()

    async def runner(wa, pn, items):
        runs.append([i.text for i in items])
        if len(runs) == 1:
            await gate.wait()

    b.add("91", "pn", Item("first"), runner)
    await asyncio.sleep(0.06)  # first run started and is blocked
    b.add("91", "pn", Item("second"), runner)
    b.add("91", "pn", Item("third"), runner)
    await asyncio.sleep(0.06)
    assert runs == [["first"]]
    gate.set()
    await asyncio.sleep(0.1)
    assert runs == [["first"], ["second", "third"]]


@pytest.mark.asyncio
async def test_users_are_independent():
    b = Batcher(text_delay=0.02, tap_delay=0.01)
    seen = []

    async def runner(wa, pn, items):
        seen.append((wa, len(items)))

    b.add("1", "pn", Item("x"), runner)
    b.add("2", "pn", Item("y"), runner)
    await asyncio.sleep(0.1)
    assert sorted(seen) == [("1", 1), ("2", 1)]

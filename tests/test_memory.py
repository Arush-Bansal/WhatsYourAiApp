import pytest

from app import memory
from app.memory import build_memory_block, pick_recent, prepare_turn
from app.store import MemoryStore, Msg


def msgs(*texts):
    return [Msg(i, "user" if i % 2 == 0 else "assistant", t) for i, t in enumerate(texts)]


def test_pick_recent_respects_budget_and_order():
    ms = msgs("a" * 400, "b" * 400, "c" * 400)  # ~104 tokens each
    got = pick_recent(ms, 220)
    assert [m.content[0] for m in got] == ["b", "c"]
    assert pick_recent(msgs("z" * 4000), 10)[0].content[0] == "z"  # always keeps the newest


@pytest.mark.asyncio
async def test_brand_lifecycle_and_card_merge():
    s = MemoryStore()
    b = await s.active_brand("91")
    assert b.name == "My brand"
    await s.update_brand(b.id, "Brew Lab", {"colors": "warm brown", "avoid": "gradients"})
    await s.update_brand(b.id, None, {"avoid": ""})
    b = await s.active_brand("91")
    assert b.name == "Brew Lab" and b.card == {"colors": "warm brown"}
    b2 = await s.create_brand("91", "Pencil Co")
    assert (await s.active_brand("91")).id == b2.id
    assert (await s.switch_brand("91", "brew")).id == b.id
    assert await s.switch_brand("91", "nope") is None
    block = build_memory_block(await s.active_brand("91"), await s.list_brands("91"), "", [])
    assert "Brew Lab" in block and "warm brown" in block and "Pencil Co" in block


@pytest.mark.asyncio
async def test_sessions_split_summarise_and_compact(monkeypatch):
    calls = []

    async def fake_summarise(prev, messages, card):
        calls.append(len(messages))
        return f"summary of {len(messages)} msgs", {"colors": "teal"}

    monkeypatch.setattr(memory, "summarise", fake_summarise)
    s = MemoryStore()
    turn = await prepare_turn(s, "91")
    await s.append_message("91", "user", "hi", turn.session.id)
    await s.append_message("91", "assistant", "hello", turn.session.id)

    # same session while chatting
    assert (await prepare_turn(s, "91")).session.id == turn.session.id

    # force a new session by switching brand: old one is summarised, facts land on the OLD brand's card
    first_brand = turn.brand
    await s.create_brand("91", "Other")
    t2 = await prepare_turn(s, "91")
    assert t2.session.id != turn.session.id
    assert calls == [2]
    assert (await s.list_brands("91"))[0].card == {"colors": "teal"} and first_brand.id != t2.brand.id
    assert t2.history == []

    # long session: older messages get folded and hidden
    for i in range(30):
        await s.append_message("91", "user", "x" * 600, t2.session.id)
    t3 = await prepare_turn(s, "91")
    assert t3.session.summary.startswith("summary of")
    assert 0 < len(t3.history) < 30
    assert "Earlier in this session" in t3.memory_block
    # the next turn sees only uncompacted messages
    assert len((await prepare_turn(s, "91")).history) == len(t3.history)

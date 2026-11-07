import pytest

from app.agent.plan import (
    PLAN_EDIT,
    PLAN_GO,
    PLAN_SKIP,
    format_plan_body,
    normalise_pointers,
    plan_buttons_payload,
    prompt_for_plan_tap,
)
from app.memory import build_memory_block
from app.session_flow import is_new_session_command, is_wrap_command, start_new, wrap_up
from app.store import FormSession, MemoryStore


def test_pointers_cap_at_nine():
    got = normalise_pointers(["  a  ", "", *("x" for _ in range(12))])
    assert got[0] == "a" and len(got) == 9


def test_plan_body_is_numbered_and_short():
    body = format_plan_body("A warm cafe mark", ["Lock the name", "Two colour directions", "You pick", "Draw a wordmark"])
    assert "1. Lock the name" in body
    assert "4. Draw a wordmark" in body
    assert "5." not in body
    assert "Go follows this" in body
    payload = plan_buttons_payload("A warm cafe mark", ["Lock the name"])
    assert [b.id for b in payload.buttons] == [PLAN_GO, PLAN_EDIT, PLAN_SKIP]


def test_plan_tap_prompts():
    pointers = ["Ask what it sells", "Sketch two palettes"]
    go = prompt_for_plan_tap(PLAN_GO, pointers, "Palette")
    assert "approved" in go and "1. Ask what it sells" in go
    edit = prompt_for_plan_tap(PLAN_EDIT, pointers, "Palette")
    assert "change the plan" in edit and "propose_plan" in edit
    skip = prompt_for_plan_tap(PLAN_SKIP, pointers, "Palette")
    assert "skipped the outline" in skip


@pytest.mark.asyncio
async def test_session_plan_lands_in_memory():
    s = MemoryStore()
    turn = await s.open_session("91", (await s.active_brand("91")).id)
    await s.update_session(turn.id, goal="Cafe logo", mode="plan", plan=["Name", "Feel", "Mark"])
    session = await s.get_session(turn.id)
    block = build_memory_block(await s.active_brand("91"), await s.list_brands("91"), "", [], session)
    assert "mode=plan" in block and "Cafe logo" in block and "1. Name" in block and "3. Mark" in block


@pytest.mark.asyncio
async def test_wrap_and_new_session_commands(monkeypatch):
    async def fake_summarise(prev, messages, card):
        return f"summary of {len(messages)}", {}

    monkeypatch.setattr("app.memory.summarise", fake_summarise)
    assert is_wrap_command("Wrap up") and is_new_session_command("new session")
    s = MemoryStore()
    first = await s.open_session("91", (await s.active_brand("91")).id)
    await s.append_message("91", "user", "hi", first.id)
    await s.append_message("91", "assistant", "hello", first.id)
    await wrap_up(s, "91")
    closed = await s.get_session(first.id)
    assert closed and closed.summarised
    await start_new(s, "91")
    brand = await s.active_brand("91")
    nxt = await s.open_session("91", brand.id)
    assert nxt.id != first.id and not nxt.summarised


@pytest.mark.asyncio
async def test_new_session_drops_active_form():
    s = MemoryStore()
    await s.save_form_session(FormSession(wa_id="91", form_id="logo_brief", step=4))
    assert await s.get_form_session("91") is not None
    await start_new(s, "91")
    assert await s.get_form_session("91") is None

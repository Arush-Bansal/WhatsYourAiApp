import httpx
import pytest

from app import forms
from app.store import MemoryStore


@pytest.fixture
def sent(monkeypatch):
    log = []

    async def text(http, pn, to, body):
        log.append(("text", body))
        return True

    async def buttons(http, pn, to, payload):
        log.append(("buttons", payload.body_text, [b.id for b in payload.buttons]))
        return True

    async def lst(http, pn, to, payload):
        log.append(("list", payload.body_text, [r.id for s in payload.sections for r in s.rows]))
        return True

    monkeypatch.setattr(forms, "send_text_reply", text)
    monkeypatch.setattr(forms, "send_interactive_buttons_reply", buttons)
    monkeypatch.setattr(forms, "send_interactive_list_reply", lst)
    return log


@pytest.mark.asyncio
async def test_logo_form_full_walkthrough(sent):
    store, http = MemoryStore(), None
    assert await forms.handle_incoming(store, http, "pn", "91", "text", "hi") is False
    assert await forms.start_form(store, http, "pn", "91", "logo_brief")

    async def say(kind, value, title=""):
        return await forms.handle_incoming(store, http, "pn", "91", kind, value, title)

    assert await say("text", "Brew Lab") is True
    assert await say("list", "f:industry:food", "Food & drink") is True
    assert await say("text", "college students") is True
    assert await say("text", "cheaper and cooler than stationery shops") is True
    assert await say("list", "f:touchpoints:social", "Social media") is True
    assert await say("text", "bold, warm, playful") is True
    assert await say("text", "skip") is True  # avoid (optional)
    assert await say("text", "just typing") is True  # button step: nudged, step unchanged
    assert await say("button", "f:style:wordmark", "Wordmark") is True
    done = await say("text", "skip")
    assert isinstance(done, forms.Completed)
    assert "Brew Lab" in done.prompt and "Food & drink" in done.prompt and "Wordmark" in done.prompt
    assert "colors:" not in done.prompt
    assert await store.get_form_session("91") is None
    assert store.submissions[0][1] == "logo_brief"


@pytest.mark.asyncio
async def test_cancel_and_stale_button(sent):
    store = MemoryStore()
    await forms.start_form(store, None, "pn", "91", "logo_brief")
    assert await forms.handle_incoming(store, None, "pn", "91", "button", "logo_quick", "Quick logo") is False
    assert await forms.handle_incoming(store, None, "pn", "91", "text", "cancel") is True
    assert await store.get_form_session("91") is None


@pytest.mark.asyncio
async def test_new_session_is_not_a_form_answer(sent):
    store = MemoryStore()
    await forms.start_form(store, None, "pn", "91", "logo_brief")
    assert await forms.handle_incoming(store, None, "pn", "91", "text", "new session") is False
    assert await store.get_form_session("91") is not None


@pytest.mark.asyncio
async def test_claim_message_dedupes():
    store = MemoryStore()
    assert await store.claim_message("m1") and not await store.claim_message("m1")


@pytest.mark.asyncio
async def test_typed_option_is_accepted_and_form_is_never_a_trap(sent):
    store = MemoryStore()
    await forms.start_form(store, None, "pn", "91", "logo_brief")
    async def say(kind, value, title=""):
        return await forms.handle_incoming(store, None, "pn", "91", kind, value, title)
    for text in ("Brew Lab",):
        await say("text", text)
    assert await say("text", "tech") is True  # typed the industry instead of tapping
    assert (await store.get_form_session("91")).step == 2
    await say("text", "students"); await say("text", "cheaper")
    # touchpoints step (list): gibberish nudges twice, then releases the user to the agent
    assert await say("text", "hello") is True
    assert await say("text", "hello again") is True
    assert await say("text", "hello???") is False
    assert await store.get_form_session("91") is None


def test_new_session_phrases():
    from app.session_flow import is_new_session_command

    assert is_new_session_command("heeyyy new session please") and is_new_session_command("start over")
    assert is_new_session_command("new sessoin please") and is_new_session_command("new seesion") and is_new_session_command("new chat")
    assert not is_new_session_command("I want a new logo") and not is_new_session_command("new shoes brand")
    assert not is_new_session_command("a coffee brand for people who want a fresh start in the morning every day")

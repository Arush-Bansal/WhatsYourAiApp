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
async def test_claim_message_dedupes():
    store = MemoryStore()
    assert await store.claim_message("m1") and not await store.claim_message("m1")

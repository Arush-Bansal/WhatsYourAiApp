import asyncio
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from app.agent import (
    WhatsAppAgentContext,
    prompt_for_button_reply,
    prompt_for_list_reply,
    prompt_for_text_message,
    run_whatsapp_turn,
)
from app.agent.voice_transcribe import transcribe_voice_to_hinglish
from app.config import VERIFY_TOKEN
from app.forms import Completed, handle_incoming
from app.security import verify_meta_signature
from app.store import Store
from app.whatsapp.client import download_whatsapp_media, send_text_reply
from app.whatsapp.parser import (
    iter_incoming_button_replies,
    iter_incoming_list_replies,
    iter_incoming_text_messages,
    iter_incoming_voice_notes,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _dispatch_result(
    result: Any,
    http: httpx.AsyncClient,
    ctx: WhatsAppAgentContext,
) -> None:
    """Send final_output as a text message when the agent skipped the send tool."""
    if ctx.reply_sent:
        return
    if result is None:
        return
    text = getattr(result, "final_output", None)
    if text and isinstance(text, str):
        if await send_text_reply(http, ctx.phone_number_id, ctx.to_wa_id, text) and ctx.store:
            await ctx.store.append_message(ctx.to_wa_id, "assistant", text[:1500])


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid hub.mode")
    if not VERIFY_TOKEN or hub_verify_token != VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    if hub_challenge is None:
        raise HTTPException(status_code=400, detail="Missing hub.challenge")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/webhook")
async def receive_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    raw = await request.body()
    try:
        verify_meta_signature(raw, request.headers.get("x-hub-signature-256"))
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        logger.warning("Webhook POST: invalid JSON")
        return {"status": "ok"}
    except HTTPException:
        raise

    # Reply after responding 200: agent turns (esp. image generation) outlast Meta's webhook timeout.
    background_tasks.add_task(
        _process_webhook, data, request.app.state.http, request.app.state.store
    )
    return {"status": "ok"}


# One user's messages are handled in order, so a fast second message sees the form state of the first.
_user_locks: dict[str, asyncio.Lock] = {}


async def _process_webhook(data: dict[str, Any], http: httpx.AsyncClient, store: Store) -> None:
    try:
        await _handle_events(data, http, store)
    except Exception:
        logger.exception("Webhook processing failed")


async def _run_agent(
    http: httpx.AsyncClient,
    store: Store,
    phone_number_id: str,
    wa_id: str,
    prompt: str,
) -> None:
    ctx = WhatsAppAgentContext(
        http=http, phone_number_id=phone_number_id, to_wa_id=wa_id, store=store
    )
    result = await run_whatsapp_turn(context=ctx, user_prompt=prompt)
    await _dispatch_result(result, http, ctx)


async def _on_user_input(
    http: httpx.AsyncClient,
    store: Store,
    phone_number_id: str,
    wa_id: str,
    kind: str,
    value: str,
    title: str,
    agent_prompt: str,
) -> None:
    """Give an active form first refusal on the input, otherwise run the agent."""
    outcome = await handle_incoming(store, http, phone_number_id, wa_id, kind, value, title)  # type: ignore[arg-type]
    if outcome is True:
        return
    if isinstance(outcome, Completed):
        agent_prompt = outcome.prompt
    await _run_agent(http, store, phone_number_id, wa_id, agent_prompt)


async def _handle_events(data: dict[str, Any], http: httpx.AsyncClient, store: Store) -> None:
    # (message_id, wa_id, phone_number_id, kind, value, title, agent_prompt); voice is handled inline.
    events: list[tuple[str, str, str, str, str, str, str]] = []
    for mid, wa, bid, title, pn in iter_incoming_button_replies(data):
        events.append((mid, wa, pn, "button", bid, title, prompt_for_button_reply(bid, title)))
    for mid, wa, rid, title, desc, pn in iter_incoming_list_replies(data):
        events.append((mid, wa, pn, "list", rid, title, prompt_for_list_reply(rid, title, desc)))
    for mid, wa, text, pn in iter_incoming_text_messages(data):
        events.append((mid, wa, pn, "text", text, "", prompt_for_text_message(text)))
    voice = list(iter_incoming_voice_notes(data))

    for mid, wa, pn, kind, value, title, agent_prompt in events:
        if not await store.claim_message(mid):
            continue
        async with _user_locks.setdefault(wa, asyncio.Lock()):
            await _on_user_input(http, store, pn, wa, kind, value, title, agent_prompt)

    for mid, wa, media_id, pn in voice:
        if not await store.claim_message(mid):
            continue
        async with _user_locks.setdefault(wa, asyncio.Lock()):
            downloaded = await download_whatsapp_media(http, media_id)
            if downloaded is None:
                await send_text_reply(
                    http, pn, wa, "Sorry, I couldn't download your voice note. Please try again."
                )
                continue
            audio_bytes, mime_type = downloaded
            hinglish = await transcribe_voice_to_hinglish(audio_bytes, mime_type)
            if hinglish is None:
                await send_text_reply(
                    http,
                    pn,
                    wa,
                    "Sorry, I couldn't transcribe your voice note. Please try again or send a text message.",
                )
                continue
            await send_text_reply(http, pn, wa, f"Transcription:\n{hinglish}")
            await _on_user_input(
                http, store, pn, wa, "text", hinglish, "", prompt_for_text_message(hinglish)
            )

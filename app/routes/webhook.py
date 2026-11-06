import base64
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
from app.batching import Item, batcher
from app.config import VERIFY_TOKEN
from app.forms import Completed, handle_incoming
from app.security import verify_meta_signature
from app.store import Store
from app.whatsapp.client import download_whatsapp_media, send_text_reply
from app.whatsapp.parser import (
    iter_incoming_button_replies,
    iter_incoming_list_replies,
    iter_incoming_media,
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


MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024


async def _process_webhook(data: dict[str, Any], http: httpx.AsyncClient, store: Store) -> None:
    try:
        await _handle_events(data, http, store)
    except Exception:
        logger.exception("Webhook processing failed")


async def _run_batch(
    http: httpx.AsyncClient,
    store: Store,
    wa_id: str,
    phone_number_id: str,
    items: list[Item],
) -> None:
    """One agent turn for everything the user sent in a burst."""
    if len(items) == 1:
        prompt = items[0].text
    else:
        numbered = "\n---\n".join(f"({i}) {it.text}" for i, it in enumerate(items, 1))
        prompt = f"The user sent {len(items)} messages in a row. Read them all, then reply once:\n{numbered}"
    parts = [p for it in items for p in it.parts]
    await _run_agent(http, store, phone_number_id, wa_id, prompt, parts)


async def _run_agent(
    http: httpx.AsyncClient,
    store: Store,
    phone_number_id: str,
    wa_id: str,
    prompt: str,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    ctx = WhatsAppAgentContext(
        http=http, phone_number_id=phone_number_id, to_wa_id=wa_id, store=store
    )
    result = await run_whatsapp_turn(context=ctx, user_prompt=prompt, attachments=attachments)
    await _dispatch_result(result, http, ctx)


async def _on_user_input(
    http: httpx.AsyncClient,
    store: Store,
    phone_number_id: str,
    wa_id: str,
    kind: str,
    value: str,
    title: str,
    item: Item,
) -> None:
    """An active form gets first refusal on the input; otherwise it joins the user's batch."""
    async with batcher.lock(wa_id):
        outcome = await handle_incoming(store, http, phone_number_id, wa_id, kind, value, title)  # type: ignore[arg-type]
        if outcome is True:
            return
        if isinstance(outcome, Completed):
            await _run_agent(http, store, phone_number_id, wa_id, outcome.prompt)
            return

    async def runner(wa: str, pn: str, items: list[Item]) -> None:
        await _run_batch(http, store, wa, pn, items)

    batcher.add(wa_id, phone_number_id, item, runner)


def _attachment_item(
    kind: str, mime: str, filename: str, caption: str, data: bytes
) -> Item | None:
    b64 = base64.b64encode(data).decode("ascii")
    label = f" with caption: {caption}" if caption else ""
    if kind == "image" or mime.startswith("image/"):
        part = {"type": "input_image", "image_url": f"data:{mime or 'image/jpeg'};base64,{b64}", "detail": "auto"}
        return Item(text=f"User sent an image{label}", parts=[part])
    if mime == "application/pdf":
        name = filename or "document.pdf"
        part = {"type": "input_file", "filename": name, "file_data": f"data:application/pdf;base64,{b64}"}
        return Item(text=f"User sent a PDF named {name!r}{label}", parts=[part])
    return None


async def _handle_events(data: dict[str, Any], http: httpx.AsyncClient, store: Store) -> None:
    for mid, wa, bid, title, pn in iter_incoming_button_replies(data):
        if await store.claim_message(mid):
            item = Item(prompt_for_button_reply(bid, title), tap=True)
            await _on_user_input(http, store, pn, wa, "button", bid, title, item)
    for mid, wa, rid, title, desc, pn in iter_incoming_list_replies(data):
        if await store.claim_message(mid):
            item = Item(prompt_for_list_reply(rid, title, desc), tap=True)
            await _on_user_input(http, store, pn, wa, "list", rid, title, item)
    for mid, wa, text, pn in iter_incoming_text_messages(data):
        if await store.claim_message(mid):
            await _on_user_input(http, store, pn, wa, "text", text, "", Item(prompt_for_text_message(text)))

    for mid, wa, media_id, pn in iter_incoming_voice_notes(data):
        if not await store.claim_message(mid):
            continue
        downloaded = await download_whatsapp_media(http, media_id)
        if downloaded is None:
            await send_text_reply(http, pn, wa, "Sorry, I couldn't download your voice note. Please try again.")
            continue
        audio_bytes, mime_type = downloaded
        hinglish = await transcribe_voice_to_hinglish(audio_bytes, mime_type)
        if hinglish is None:
            await send_text_reply(
                http, pn, wa, "Sorry, I couldn't transcribe your voice note. Please try again or send a text message."
            )
            continue
        await send_text_reply(http, pn, wa, f"Transcription:\n{hinglish}")
        await _on_user_input(http, store, pn, wa, "text", hinglish, "", Item(prompt_for_text_message(hinglish)))

    for mid, wa, media_id, pn, kind, mime, filename, caption in iter_incoming_media(data):
        if not await store.claim_message(mid):
            continue
        downloaded = await download_whatsapp_media(http, media_id)
        if downloaded is None:
            await send_text_reply(http, pn, wa, "Sorry, I couldn't download that file. Please try again.")
            continue
        body, dl_mime = downloaded
        mime = dl_mime or mime
        if len(body) > MAX_ATTACHMENT_BYTES:
            await send_text_reply(http, pn, wa, "That file is too large for me (15 MB max). Could you send a smaller one?")
            continue
        item = _attachment_item(kind, mime, filename, caption, body)
        if item is None:
            await send_text_reply(http, pn, wa, "I can read images and PDFs for now. Could you send it as one of those?")
            continue
        await _on_user_input(http, store, pn, wa, "attachment", "", "", item)

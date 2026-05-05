import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.agent import (
    WhatsAppAgentContext,
    prompt_for_button_reply,
    prompt_for_list_reply,
    prompt_for_text_message,
    run_whatsapp_turn,
)
from app.agent.voice_transcribe import transcribe_voice_to_hinglish
from app.config import VERIFY_TOKEN
from app.dedupe import already_processed, mark_processed
from app.security import verify_meta_signature
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
    phone_number_id: str,
    to_wa_id: str,
) -> None:
    """Send final_output as a text message when the agent skipped the send tool."""
    if result is None:
        return
    text = getattr(result, "final_output", None)
    if text and isinstance(text, str):
        await send_text_reply(http, phone_number_id, to_wa_id, text)


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
async def receive_webhook(request: Request) -> dict[str, str]:
    raw = await request.body()
    try:
        verify_meta_signature(raw, request.headers.get("x-hub-signature-256"))
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        logger.warning("Webhook POST: invalid JSON")
        return {"status": "ok"}
    except HTTPException:
        raise

    http: httpx.AsyncClient = request.app.state.http

    for message_id, from_wa_id, bid, title, phone_number_id in iter_incoming_button_replies(
        data
    ):
        if already_processed(message_id):
            continue
        mark_processed(message_id)
        ctx = WhatsAppAgentContext(
            http=http,
            phone_number_id=phone_number_id,
            to_wa_id=from_wa_id,
        )
        prompt = prompt_for_button_reply(bid, title)
        result = await run_whatsapp_turn(context=ctx, user_prompt=prompt)
        await _dispatch_result(result, http, phone_number_id, from_wa_id)

    for (
        message_id,
        from_wa_id,
        row_id,
        title,
        description,
        phone_number_id,
    ) in iter_incoming_list_replies(data):
        if already_processed(message_id):
            continue
        mark_processed(message_id)
        ctx = WhatsAppAgentContext(
            http=http,
            phone_number_id=phone_number_id,
            to_wa_id=from_wa_id,
        )
        prompt = prompt_for_list_reply(row_id, title, description)
        result = await run_whatsapp_turn(context=ctx, user_prompt=prompt)
        await _dispatch_result(result, http, phone_number_id, from_wa_id)

    for message_id, from_wa_id, text_body, phone_number_id in iter_incoming_text_messages(
        data
    ):
        if already_processed(message_id):
            continue
        mark_processed(message_id)
        ctx = WhatsAppAgentContext(
            http=http,
            phone_number_id=phone_number_id,
            to_wa_id=from_wa_id,
        )
        prompt = prompt_for_text_message(text_body)
        result = await run_whatsapp_turn(context=ctx, user_prompt=prompt)
        await _dispatch_result(result, http, phone_number_id, from_wa_id)

    for message_id, from_wa_id, media_id, phone_number_id in iter_incoming_voice_notes(
        data
    ):
        if already_processed(message_id):
            continue
        mark_processed(message_id)
        ctx = WhatsAppAgentContext(
            http=http,
            phone_number_id=phone_number_id,
            to_wa_id=from_wa_id,
        )
        downloaded = await download_whatsapp_media(http, media_id)
        if downloaded is None:
            await send_text_reply(
                http,
                phone_number_id,
                from_wa_id,
                "Sorry, I couldn't download your voice note. Please try again.",
            )
            continue
        audio_bytes, mime_type = downloaded
        hinglish = await transcribe_voice_to_hinglish(audio_bytes, mime_type)
        if hinglish is None:
            await send_text_reply(
                http,
                phone_number_id,
                from_wa_id,
                "Sorry, I couldn't transcribe your voice note. Please try again or send a text message.",
            )
            continue
        await send_text_reply(
            http,
            phone_number_id,
            from_wa_id,
            f"Transcription:\n{hinglish}",
        )
        prompt = prompt_for_text_message(hinglish)
        result = await run_whatsapp_turn(context=ctx, user_prompt=prompt)
        await _dispatch_result(result, http, phone_number_id, from_wa_id)

    return {"status": "ok"}

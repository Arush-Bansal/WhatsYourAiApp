import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.agent import (
    WhatsAppAgentContext,
    prompt_for_button_reply,
    prompt_for_list_reply,
    prompt_for_text_message,
    run_whatsapp_turn,
)
from app.config import VERIFY_TOKEN
from app.dedupe import already_processed, mark_processed
from app.security import verify_meta_signature
from app.whatsapp.parser import (
    iter_incoming_button_replies,
    iter_incoming_list_replies,
    iter_incoming_text_messages,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
        await run_whatsapp_turn(context=ctx, user_prompt=prompt)

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
        await run_whatsapp_turn(context=ctx, user_prompt=prompt)

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
        await run_whatsapp_turn(context=ctx, user_prompt=prompt)

    return {"status": "ok"}

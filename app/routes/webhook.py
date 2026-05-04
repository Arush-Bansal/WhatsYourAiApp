import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.config import VERIFY_TOKEN
from app.dedupe import already_processed, mark_processed
from app.security import verify_meta_signature
from app.whatsapp.client import (
    send_interactive_buttons_reply,
    send_interactive_flow_reply,
    send_interactive_list_reply,
    send_text_reply,
)
from app.whatsapp.parser import (
    iter_incoming_button_replies,
    iter_incoming_flow_nfm_replies,
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
        ack = f'You tapped "{title}"' + (f" (id: {bid})" if bid else "") + "."
        await send_text_reply(http, phone_number_id, from_wa_id, ack)

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
        parts = [f'You picked list row "{title}"']
        if row_id:
            parts.append(f"(id: {row_id})")
        if description:
            parts.append(f"— {description}")
        ack = " ".join(parts) + "."
        await send_text_reply(http, phone_number_id, from_wa_id, ack)

    for message_id, from_wa_id, response_json, phone_number_id in iter_incoming_flow_nfm_replies(
        data
    ):
        if already_processed(message_id):
            continue
        mark_processed(message_id)
        preview = response_json[:600] + ("…" if len(response_json) > 600 else "")
        ack = f"Flow submitted. Data: {preview}" if preview else "Flow submitted."
        await send_text_reply(http, phone_number_id, from_wa_id, ack)

    for message_id, from_wa_id, text_body, phone_number_id in iter_incoming_text_messages(
        data
    ):
        if already_processed(message_id):
            continue
        mark_processed(message_id)

        cmd = text_body.strip().lower()
        if cmd == "buttons":
            await send_interactive_buttons_reply(
                http,
                phone_number_id,
                from_wa_id,
                body_text="Here are quick-reply buttons. Tap one.",
            )
        elif cmd in ("list", "dropdown"):
            await send_interactive_list_reply(
                http,
                phone_number_id,
                from_wa_id,
                body_text="Tap the button to open the list (dropdown-style). Pick one row.",
            )
        elif cmd == "form":
            sent = await send_interactive_flow_reply(
                http,
                phone_number_id,
                from_wa_id,
                body_text="Open the form to answer (including multi-select if your Flow defines it).",
            )
            if not sent:
                await send_interactive_list_reply(
                    http,
                    phone_number_id,
                    from_wa_id,
                    body_text=(
                        "No Flow configured (set WHATSAPP_FLOW_ID and WHATSAPP_FLOW_SCREEN). "
                        "Here is a list picker instead. True multi-select needs a Flow with CheckboxGroup."
                    ),
                )
        else:
            reply = f'You typed: "{text_body}"'
            await send_text_reply(http, phone_number_id, from_wa_id, reply)

    return {"status": "ok"}

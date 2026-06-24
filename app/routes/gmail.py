from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.agent import GmailAgentContext, prompt_for_email, run_gmail_turn
from app.config import GMAIL_MAILBOX_EMAIL
from app.dedupe import already_processed, mark_processed
from app.gmail.client import get_message, list_history, mark_as_read, register_watch, send_reply
from app.gmail.parser import iter_history_message_ids, parse_incoming_message
from app.gmail.payloads import GmailReplyPayload
from app.gmail.state import load_last_history_id, save_last_history_id
from app.security import verify_gmail_watch_secret, verify_pubsub_push

logger = logging.getLogger(__name__)

router = APIRouter()


def _schedule_background(coro: Any) -> None:
    async def _wrapper() -> None:
        try:
            await coro
        except Exception:
            logger.exception("Gmail background task failed")

    asyncio.create_task(_wrapper())


async def _dispatch_gmail_result(
    result: Any,
    http: httpx.AsyncClient,
    ctx: GmailAgentContext,
) -> None:
    """Send final_output as a reply when the agent skipped the send tool."""
    if result is None:
        return
    text = getattr(result, "final_output", None)
    if text and isinstance(text, str):
        payload = GmailReplyPayload(body_text=text)
        in_reply_to = ctx.message_id_header or ctx.message_id
        references = ctx.references or in_reply_to
        await send_reply(
            http,
            to_email=ctx.from_email,
            thread_id=ctx.thread_id,
            subject=ctx.subject,
            in_reply_to=in_reply_to,
            references=references,
            payload=payload,
        )


async def _process_incoming_message(
    http: httpx.AsyncClient,
    message_id: str,
) -> None:
    if already_processed(message_id):
        return

    message = await get_message(http, message_id)
    if message is None:
        return

    mailbox = GMAIL_MAILBOX_EMAIL.lower()
    parsed = parse_incoming_message(message, mailbox_email=mailbox)
    if parsed is None:
        return

    (
        gmail_message_id,
        thread_id,
        from_email,
        _to_email,
        subject,
        body_plain,
        message_id_header,
    ) = parsed

    if already_processed(gmail_message_id):
        return
    mark_processed(gmail_message_id)

    ctx = GmailAgentContext(
        http=http,
        mailbox_email=mailbox,
        thread_id=thread_id,
        message_id=gmail_message_id,
        from_email=from_email,
        subject=subject,
        message_id_header=message_id_header,
        references=message_id_header,
    )
    prompt = prompt_for_email(from_email, subject, body_plain)
    result = await run_gmail_turn(context=ctx, user_prompt=prompt)
    await _dispatch_gmail_result(result, http, ctx)
    await mark_as_read(http, gmail_message_id)


async def _sync_history(http: httpx.AsyncClient, notification_history_id: str) -> None:
    start_history_id = load_last_history_id()
    if not start_history_id:
        save_last_history_id(notification_history_id)
        return

    history_response = await list_history(http, start_history_id)
    if history_response is None:
        save_last_history_id(notification_history_id)
        return

    for message_id in iter_history_message_ids(history_response):
        await _process_incoming_message(http, message_id)

    new_history_id = str(history_response.get("historyId") or notification_history_id)
    save_last_history_id(new_history_id)


async def _handle_pubsub_push(http: httpx.AsyncClient, data: dict[str, Any]) -> None:
    message = data.get("message") or {}
    if not isinstance(message, dict):
        return

    raw_data = message.get("data")
    if not raw_data or not isinstance(raw_data, str):
        return

    try:
        decoded = base64.b64decode(raw_data).decode("utf-8")
        notification = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        logger.warning("Gmail push: invalid Pub/Sub message data")
        return

    history_id = str(notification.get("historyId") or "")
    if not history_id:
        return

    await _sync_history(http, history_id)


@router.post("/gmail/push", response_model=None)
async def gmail_push(request: Request) -> Response | dict[str, str]:
    raw = await request.body()
    try:
        verify_pubsub_push(request.headers.get("authorization"))
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        logger.warning("Gmail push POST: invalid JSON")
        return Response(status_code=200)
    except HTTPException:
        raise

    http: httpx.AsyncClient = request.app.state.http
    _schedule_background(_handle_pubsub_push(http, data))
    return Response(status_code=200)


@router.post("/gmail/watch")
async def gmail_watch(request: Request) -> dict[str, Any]:
    verify_gmail_watch_secret(request.headers.get("x-gmail-watch-secret"))
    http: httpx.AsyncClient = request.app.state.http
    result = await register_watch(http)
    if result is None:
        raise HTTPException(status_code=503, detail="Failed to register Gmail watch")

    history_id = str(result.get("historyId") or "")
    if history_id:
        save_last_history_id(history_id)

    return {"status": "ok", "historyId": history_id, "expiration": result.get("expiration")}

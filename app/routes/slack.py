from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.agent import (
    SlackAgentContext,
    prompt_for_slack_button_action,
    prompt_for_slack_menu_selection,
    prompt_for_text_message,
    run_slack_turn,
)
from app.agent.voice_transcribe import transcribe_voice_to_hinglish
from app.dedupe import already_processed, mark_processed
from app.security import verify_slack_signature
from app.slack.client import download_slack_file, send_text_reply
from app.slack.parser import (
    iter_button_actions,
    iter_incoming_audio_files,
    iter_incoming_dm_text,
    iter_select_actions,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _dispatch_slack_result(
    result: Any,
    http: httpx.AsyncClient,
    channel_id: str,
    ctx: SlackAgentContext,
) -> None:
    """Send final_output as a text message when the agent skipped the send tool."""
    if ctx.reply_sent:
        return
    if result is None:
        return
    text = getattr(result, "final_output", None)
    if text and isinstance(text, str):
        await send_text_reply(http, channel_id, text)


async def _process_dm_text(
    http: httpx.AsyncClient,
    channel_id: str,
    user_id: str,
    text_body: str,
) -> None:
    ctx = SlackAgentContext(http=http, channel_id=channel_id, user_id=user_id)
    prompt = prompt_for_text_message(text_body)
    result = await run_slack_turn(context=ctx, user_prompt=prompt)
    await _dispatch_slack_result(result, http, channel_id, ctx)


async def _process_audio_file(
    http: httpx.AsyncClient,
    channel_id: str,
    user_id: str,
    file_id: str,
) -> None:
    ctx = SlackAgentContext(http=http, channel_id=channel_id, user_id=user_id)
    downloaded = await download_slack_file(http, file_id)
    if downloaded is None:
        await send_text_reply(
            http,
            channel_id,
            "Sorry, I couldn't download your audio file. Please try again.",
        )
        return
    audio_bytes, mime_type = downloaded
    hinglish = await transcribe_voice_to_hinglish(audio_bytes, mime_type)
    if hinglish is None:
        await send_text_reply(
            http,
            channel_id,
            "Sorry, I couldn't transcribe your audio. Please try again or send a text message.",
        )
        return
    await send_text_reply(http, channel_id, f"Transcription:\n{hinglish}")
    prompt = prompt_for_text_message(hinglish)
    result = await run_slack_turn(context=ctx, user_prompt=prompt)
    await _dispatch_slack_result(result, http, channel_id, ctx)


async def _process_button_action(
    http: httpx.AsyncClient,
    dedupe_id: str,
    channel_id: str,
    user_id: str,
    action_id: str,
    button_text: str,
    value: str,
) -> None:
    if already_processed(dedupe_id):
        return
    mark_processed(dedupe_id)
    ctx = SlackAgentContext(http=http, channel_id=channel_id, user_id=user_id)
    prompt = prompt_for_slack_button_action(action_id, button_text, value)
    result = await run_slack_turn(context=ctx, user_prompt=prompt)
    await _dispatch_slack_result(result, http, channel_id, ctx)


async def _process_select_action(
    http: httpx.AsyncClient,
    dedupe_id: str,
    channel_id: str,
    user_id: str,
    action_id: str,
    option_value: str,
    option_text: str,
) -> None:
    if already_processed(dedupe_id):
        return
    mark_processed(dedupe_id)
    ctx = SlackAgentContext(http=http, channel_id=channel_id, user_id=user_id)
    prompt = prompt_for_slack_menu_selection(action_id, option_value, option_text)
    result = await run_slack_turn(context=ctx, user_prompt=prompt)
    await _dispatch_slack_result(result, http, channel_id, ctx)


async def _handle_event_callback(http: httpx.AsyncClient, data: dict[str, Any]) -> None:
    for _event_id, channel_id, user_id, text_body in iter_incoming_dm_text(data):
        await _process_dm_text(http, channel_id, user_id, text_body)

    for _event_id, channel_id, user_id, file_id in iter_incoming_audio_files(data):
        await _process_audio_file(http, channel_id, user_id, file_id)


async def _handle_interactivity(http: httpx.AsyncClient, data: dict[str, Any]) -> None:
    for (
        dedupe_id,
        channel_id,
        user_id,
        action_id,
        button_text,
        value,
    ) in iter_button_actions(data):
        await _process_button_action(
            http, dedupe_id, channel_id, user_id, action_id, button_text, value
        )

    for (
        dedupe_id,
        channel_id,
        user_id,
        action_id,
        option_value,
        option_text,
    ) in iter_select_actions(data):
        await _process_select_action(
            http, dedupe_id, channel_id, user_id, action_id, option_value, option_text
        )


def _schedule_background(coro: Any) -> None:
    async def _wrapper() -> None:
        try:
            await coro
        except Exception:
            logger.exception("Slack background task failed")

    asyncio.create_task(_wrapper())


@router.post("/slack/events", response_model=None)
async def slack_events(request: Request) -> Response | dict[str, str]:
    raw = await request.body()
    try:
        verify_slack_signature(
            raw,
            request.headers.get("x-slack-signature"),
            request.headers.get("x-slack-request-timestamp"),
        )
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        logger.warning("Slack events POST: invalid JSON")
        return {"status": "ok"}
    except HTTPException:
        raise

    if data.get("type") == "url_verification":
        challenge = data.get("challenge")
        if challenge is None:
            raise HTTPException(status_code=400, detail="Missing challenge")
        return {"challenge": str(challenge)}

    if data.get("type") == "event_callback":
        event_id = str(data.get("event_id") or "")
        if event_id:
            if already_processed(event_id):
                return {"status": "ok"}
            mark_processed(event_id)
        http: httpx.AsyncClient = request.app.state.http
        _schedule_background(_handle_event_callback(http, data))
        return {"status": "ok"}

    return {"status": "ok"}


@router.post("/slack/interactions")
async def slack_interactions(request: Request) -> Response:
    raw = await request.body()
    try:
        verify_slack_signature(
            raw,
            request.headers.get("x-slack-signature"),
            request.headers.get("x-slack-request-timestamp"),
        )
        form = parse_qs(raw.decode("utf-8"))
        payload_raw = (form.get("payload") or [""])[0]
        data = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        logger.warning("Slack interactions POST: invalid JSON")
        return Response(status_code=200)
    except HTTPException:
        raise

    http: httpx.AsyncClient = request.app.state.http
    _schedule_background(_handle_interactivity(http, data))
    return Response(status_code=200)

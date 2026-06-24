from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper, function_tool

from app.agent.context import SlackAgentContext
from app.slack.client import (
    send_interactive_buttons_reply,
    send_interactive_menu_reply,
    send_text_reply,
)
from app.slack.payloads import InteractiveButtonsPayload, InteractiveMenuPayload


@function_tool
async def send_slack_text(
    wrapper: RunContextWrapper[SlackAgentContext],
    body: Annotated[str, "Plain text shown to the user in Slack (keep concise)."],
) -> str:
    """Send a plain Slack message to the current user."""
    c = wrapper.context
    ok = await send_text_reply(c.http, c.channel_id, body)
    if ok:
        c.reply_sent = True
    return "ok:text_sent" if ok else "error:text_not_sent"


@function_tool
async def send_slack_interactive_buttons(
    wrapper: RunContextWrapper[SlackAgentContext],
    payload: InteractiveButtonsPayload,
) -> str:
    """Send an interactive button message (1–5 buttons)."""
    c = wrapper.context
    ok = await send_interactive_buttons_reply(c.http, c.channel_id, payload)
    if ok:
        c.reply_sent = True
    return "ok:buttons_sent" if ok else "error:buttons_not_sent"


@function_tool
async def send_slack_interactive_menu(
    wrapper: RunContextWrapper[SlackAgentContext],
    payload: InteractiveMenuPayload,
) -> str:
    """Send an interactive select menu (max 10 options)."""
    c = wrapper.context
    ok = await send_interactive_menu_reply(c.http, c.channel_id, payload)
    if ok:
        c.reply_sent = True
    return "ok:menu_sent" if ok else "error:menu_not_sent"

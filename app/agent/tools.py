from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper, function_tool

from app.agent.context import BaseAgentContext, WhatsAppAgentContext
from app.whatsapp.client import (
    send_interactive_buttons_reply,
    send_interactive_list_reply,
    send_text_reply,
)
from app.whatsapp.payloads import InteractiveButtonsPayload, InteractiveListPayload

Section = Literal[
    "overview",
    "services",
    "hours",
    "pricing",
    "insurance",
    "faqs",
    "booking",
    "contact",
    "all",
]


@function_tool
async def get_business_details(
    wrapper: RunContextWrapper[BaseAgentContext],
    section: Annotated[
        Section,
        "Which slice of business info to return (full pricing, hours, FAQs, etc.).",
    ],
) -> str:
    """Return structured business knowledge for the assistant; does not message the user."""
    return wrapper.context.business.section(section)


@function_tool
async def send_whatsapp_text(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    body: Annotated[str, "Plain text shown to the user in WhatsApp (keep concise)."],
) -> str:
    """Send a plain WhatsApp text message to the current user."""
    c = wrapper.context
    ok = await send_text_reply(c.http, c.phone_number_id, c.to_wa_id, body)
    if ok:
        c.reply_sent = True
    return "ok:text_sent" if ok else "error:text_not_sent"


@function_tool
async def send_whatsapp_interactive_buttons(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    payload: InteractiveButtonsPayload,
) -> str:
    """Send an interactive quick-reply button message (1–3 buttons, 20-char titles)."""
    c = wrapper.context
    ok = await send_interactive_buttons_reply(
        c.http, c.phone_number_id, c.to_wa_id, payload
    )
    if ok:
        c.reply_sent = True
    return "ok:buttons_sent" if ok else "error:buttons_not_sent"


@function_tool
async def send_whatsapp_interactive_list(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    payload: InteractiveListPayload,
) -> str:
    """Send an interactive list message (max 10 rows total across sections)."""
    c = wrapper.context
    ok = await send_interactive_list_reply(
        c.http, c.phone_number_id, c.to_wa_id, payload
    )
    if ok:
        c.reply_sent = True
    return "ok:list_sent" if ok else "error:list_not_sent"

from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper, function_tool

from app.agent.context import BaseAgentContext, WhatsAppAgentContext
from app.forms import FORMS, start_form
from app.images import generate_image
from app.whatsapp.client import (
    send_image_reply,
    send_interactive_buttons_reply,
    send_interactive_list_reply,
    send_text_reply,
    upload_whatsapp_media,
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


@function_tool
async def generate_and_send_image(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    prompt: Annotated[
        str,
        "Detailed image prompt: subject, style, palette (hex codes if known), composition, mood.",
    ],
    caption: Annotated[str | None, "Optional short caption shown under the image (max 1024 chars)."] = None,
    orientation: Annotated[
        Literal["square", "landscape", "portrait"],
        "Aspect ratio of the image.",
    ] = "square",
) -> str:
    """Generate an image from the prompt and send it to the current user on WhatsApp."""
    c = wrapper.context
    size = {"square": "1024x1024", "landscape": "1536x1024", "portrait": "1024x1536"}[orientation]
    image = await generate_image(prompt, size)
    if image is None:
        return "error:image_generation_failed"
    media_id = await upload_whatsapp_media(c.http, c.phone_number_id, image, "image/jpeg")
    if media_id is None:
        return "error:image_upload_failed"
    ok = await send_image_reply(c.http, c.phone_number_id, c.to_wa_id, media_id, caption)
    if ok:
        c.reply_sent = True
    return "ok:image_sent" if ok else "error:image_not_sent"


@function_tool
async def start_form_flow(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    form_id: Annotated[Literal["logo_brief"], "Which form to start."],
) -> str:
    """Start a step-by-step form with the user (questions, buttons and lists are sent for you).

    After this returns ok, stop: the form collects the answers itself and you will be re-invoked
    with the finished answers.
    """
    c = wrapper.context
    if c.store is None or form_id not in FORMS:
        return "error:form_unavailable"
    ok = await start_form(c.store, c.http, c.phone_number_id, c.to_wa_id, form_id)
    if ok:
        c.reply_sent = True
    return "ok:form_started" if ok else "error:form_not_started"

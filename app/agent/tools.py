from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper, function_tool

from app.agent.context import BaseAgentContext, WhatsAppAgentContext
from app.agent.plan import MAX_POINTERS, MIN_POINTERS, normalise_pointers, plan_buttons_payload
from app.audio import synthesize_speech
from app.forms import FORMS, start_form
from app.memory import CARD_FIELDS
from app.store import SESSION_MODES
from app.images import generate_image
from app.whatsapp.client import (
    send_audio_reply,
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


async def record_assistant(c: WhatsAppAgentContext, text: str) -> None:
    """Remember what we sent, so the next turn has the conversation context."""
    if c.store is not None:
        await c.store.append_message(c.to_wa_id, "assistant", text[:1500], c.session_id)


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
        await record_assistant(c, body)
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
        titles = " | ".join(f"{b.title} (id {b.id})" for b in payload.buttons)
        await record_assistant(c, f"{payload.body_text}\n[buttons: {titles}]")
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
        rows = " | ".join(f"{r.title} (id {r.id})" for sec in payload.sections for r in sec.rows)
        await record_assistant(c, f"{payload.body_text}\n[list: {rows}]")
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
        await record_assistant(c, f"[sent an image] prompt: {prompt}" + (f"\ncaption: {caption}" if caption else ""))
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
        await record_assistant(c, f"[started the {form_id} form; the user is answering its questions]")
    return "ok:form_started" if ok else "error:form_not_started"


@function_tool
async def send_voice_reply(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    text: Annotated[
        str,
        "What to say aloud, written the way a person talks: contractions, short sentences, the user's own "
        "language/Hinglish mix, no markdown or bullets, say colors by name instead of hex codes, under ~1000 chars.",
    ],
    style: Annotated[str | None, "Optional delivery notes, e.g. 'calm and encouraging'."] = None,
) -> str:
    """Send a spoken voice note. Only use when the user explicitly asks for audio or a voice reply."""
    c = wrapper.context
    audio = await synthesize_speech(text, style)
    if audio is None:
        return "error:speech_failed"
    media_id = await upload_whatsapp_media(c.http, c.phone_number_id, audio, "audio/ogg", "voice.ogg")
    if media_id is None:
        return "error:audio_upload_failed"
    ok = await send_audio_reply(c.http, c.phone_number_id, c.to_wa_id, media_id)
    if ok:
        c.reply_sent = True
        await record_assistant(c, f"[sent a voice note saying] {text}")
    return "ok:voice_sent" if ok else "error:voice_not_sent"


@function_tool
async def update_brand_card(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    brand_name: Annotated[str | None, "Set or correct the brand's name."] = None,
    category: Annotated[str | None, "What it sells / its category. Empty string clears."] = None,
    audience: Annotated[str | None, "Who it is for and when they meet the brand."] = None,
    difference: Annotated[str | None, "The one win over the usual alternative."] = None,
    touchpoints: Annotated[str | None, "Where the brand shows up most."] = None,
    personality: Annotated[str | None, "3 words for how it should feel."] = None,
    avoid: Annotated[str | None, "What it must not look like."] = None,
    style: Annotated[str | None, "Preferred logo style / mark type."] = None,
    colors: Annotated[str | None, "Palette decisions (roles and hex)."] = None,
    fonts: Annotated[str | None, "Type decisions."] = None,
    tagline: Annotated[str | None, "Tagline or descriptor."] = None,
    logo_notes: Annotated[str | None, "Decisions about the logo."] = None,
    preferences: Annotated[str | None, "Lasting likes and dislikes."] = None,
    locked: Annotated[str | None, "Things the user approved and wants kept."] = None,
) -> str:
    """Save durable facts about the active brand to its memory card. Use short phrases; only what the user
    stated or approved. Call it whenever the user settles something worth remembering. Costs nothing to the user."""
    c = wrapper.context
    if c.store is None or c.brand_id is None:
        return "error:no_memory"
    values = {
        "category": category, "audience": audience, "difference": difference, "touchpoints": touchpoints,
        "personality": personality, "avoid": avoid, "style": style, "colors": colors, "fonts": fonts,
        "tagline": tagline, "logo_notes": logo_notes, "preferences": preferences, "locked": locked,
    }
    patch = {k: v for k, v in values.items() if v is not None and k in CARD_FIELDS}
    await c.store.update_brand(c.brand_id, brand_name, patch)
    return "ok:saved"


@function_tool
async def create_brand(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    name: Annotated[str, "Name of the new brand."],
) -> str:
    """Start a new brand and make it the active one (use when the user begins working on a different brand)."""
    c = wrapper.context
    if c.store is None:
        return "error:no_memory"
    brand = await c.store.create_brand(c.to_wa_id, name)
    c.brand_id = brand.id
    return f"ok:created_and_active:{brand.name}"


@function_tool
async def switch_brand(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    name: Annotated[str, "Name (or part of the name) of an existing brand."],
) -> str:
    """Switch the active brand to one the user already has."""
    c = wrapper.context
    if c.store is None:
        return "error:no_memory"
    brand = await c.store.switch_brand(c.to_wa_id, name)
    if brand is None:
        names = ", ".join(b.name for b in await c.store.list_brands(c.to_wa_id))
        return f"error:not_found; the user's brands are: {names}"
    c.brand_id = brand.id
    return f"ok:active:{brand.name}"


@function_tool
async def propose_plan(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    goal: Annotated[str, "One line: what this session is trying to get done."],
    pointers: Annotated[
        list[str],
        "1–9 short pointers outlining the process (what happens, in order). Relatable, not jargon. "
        "Do not pad to 9; match the job.",
    ],
) -> str:
    """Send PlanSkill: a numbered flow outline plus Go / Change plan / Just do it. Then stop and wait."""
    c = wrapper.context
    steps = normalise_pointers(pointers)
    if len(steps) < MIN_POINTERS:
        return "error:need_pointers"
    if len(steps) > MAX_POINTERS:
        steps = steps[:MAX_POINTERS]
    if c.store is not None and c.session_id is not None:
        await c.store.update_session(c.session_id, goal=goal, mode="plan", plan=steps)
    payload = plan_buttons_payload(goal, steps)
    ok = await send_interactive_buttons_reply(c.http, c.phone_number_id, c.to_wa_id, payload)
    if ok:
        c.reply_sent = True
        await record_assistant(c, payload.body_text)
    return "ok:plan_sent" if ok else "error:plan_not_sent"


@function_tool
async def set_session(
    wrapper: RunContextWrapper[WhatsAppAgentContext],
    goal: Annotated[str | None, "Update this session's goal."] = None,
    mode: Annotated[
        Literal["plan", "execute", "critique", "explore"] | None,
        "plan = waiting on the outline; execute = doing it; critique = review; explore = open chat.",
    ] = None,
) -> str:
    """Set this session's goal or mode without messaging the user."""
    c = wrapper.context
    if c.store is None or c.session_id is None:
        return "error:no_session"
    if mode is not None and mode not in SESSION_MODES:
        return "error:bad_mode"
    session = await c.store.update_session(c.session_id, goal=goal, mode=mode)
    return f"ok:mode={session.mode}"

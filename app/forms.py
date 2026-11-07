"""Step-by-step WhatsApp forms. Handled deterministically (no LLM) while a form is active."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from app.session_flow import is_new_session_command, is_wrap_command
from app.store import DEFAULT_BRAND_NAME, FormSession, Store
from app.whatsapp.client import (
    send_interactive_buttons_reply,
    send_interactive_list_reply,
    send_text_reply,
)
from app.whatsapp.payloads import (
    InteractiveButtonsPayload,
    InteractiveListPayload,
    ListRow,
    ListSection,
    ReplyButton,
)

logger = logging.getLogger(__name__)

ID_PREFIX = "f:"


@dataclass(frozen=True)
class Option:
    id: str
    title: str  # buttons: <=20 chars, list rows: <=24 chars
    description: str | None = None


@dataclass(frozen=True)
class Step:
    key: str
    prompt: str
    kind: Literal["text", "buttons", "list"] = "text"
    options: tuple[Option, ...] = ()
    optional: bool = False
    list_button_label: str = "Choose"


@dataclass(frozen=True)
class Form:
    id: str
    title: str
    steps: tuple[Step, ...]
    completion_instruction: str


FORMS: dict[str, Form] = {
    "logo_brief": Form(
        id="logo_brief",
        title="Logo brief",
        steps=(
            Step("brand_name", "What's the brand or business name?"),
            Step(
                "industry",
                "Which industry is it in?",
                kind="list",
                list_button_label="Pick industry",
                options=(
                    Option("food", "Food & drink"),
                    Option("tech", "Tech / SaaS"),
                    Option("fashion", "Fashion & beauty"),
                    Option("health", "Health & wellness"),
                    Option("edu", "Education"),
                    Option("finance", "Finance"),
                    Option("creative", "Creative / agency"),
                    Option("retail", "Retail / e-commerce"),
                    Option("other", "Something else"),
                ),
            ),
            Step("audience", "Who is it for, and when do they meet the brand? (e.g. college students buying stationery on campus)"),
            Step("difference", "What makes it better or different than the usual alternative? One line is plenty."),
            Step(
                "touchpoints",
                "Where will the logo show up the most?",
                kind="list",
                list_button_label="Pick one",
                options=(
                    Option("packaging", "Packaging / product"),
                    Option("app_web", "App or website"),
                    Option("social", "Social media"),
                    Option("shopfront", "Shop / signage"),
                    Option("print", "Print / merch"),
                    Option("everywhere", "Everywhere"),
                ),
            ),
            Step("personality", "Give me 3 words for how the brand should feel (e.g. bold, warm, minimal)."),
            Step("avoid", "Anything it must NOT look like? A brand to steer away from, or a style you dislike. Reply *skip* if none.", optional=True),
            Step(
                "style",
                "Which logo style do you prefer?",
                kind="buttons",
                options=(
                    Option("wordmark", "Wordmark"),
                    Option("symbol_name", "Symbol + name"),
                    Option("icon", "Icon only"),
                ),
            ),
            Step(
                "colors",
                "Any colors in mind? Send names or hex codes, or reply *skip* and I'll choose.",
                optional=True,
            ),
        ),
        completion_instruction=(
            "The user finished the logo brief form. Write one detailed image prompt from these answers "
            "(mark type from the chosen style, palette with hex codes as a main/partner/neutral system, simple geometry that "
            "works tiny and in one colour, avoid category cliches and any rival named in 'avoid', plain background, no mockups) and call "
            "generate_and_send_image. Afterwards offer to adjust colors, style or layout."
        ),
    ),
}

CANCEL_WORDS = {"cancel", "stop", "exit", "quit", "menu", "back"}
MAX_NUDGES = 2  # unmatched replies on a button/list step before we let the form go


def _match_option(step: Step, text: str) -> Option | None:
    t = re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
    if not t:
        return None
    for o in step.options:
        if t in (o.id.lower(), re.sub(r"[^a-z0-9 ]", "", o.title.lower()).strip()):
            return o
    for o in step.options:
        if t in re.sub(r"[^a-z0-9 ]", "", o.title.lower()):
            return o
    return None
SKIP_WORDS = {"skip", "-"}


@dataclass
class Completed:
    """The form finished; run the agent with this prompt."""

    prompt: str


async def _send_step(
    http: httpx.AsyncClient, phone_number_id: str, wa_id: str, form: Form, index: int
) -> None:
    step = form.steps[index]
    header = f"({index + 1}/{len(form.steps)}) "
    body = header + step.prompt
    if step.kind == "buttons":
        await send_interactive_buttons_reply(
            http,
            phone_number_id,
            wa_id,
            InteractiveButtonsPayload(
                body_text=body,
                buttons=[
                    ReplyButton(id=f"{ID_PREFIX}{step.key}:{o.id}", title=o.title) for o in step.options
                ],
            ),
        )
    elif step.kind == "list":
        await send_interactive_list_reply(
            http,
            phone_number_id,
            wa_id,
            InteractiveListPayload(
                body_text=body,
                button_label=step.list_button_label,
                sections=[
                    ListSection(
                        rows=[
                            ListRow(
                                id=f"{ID_PREFIX}{step.key}:{o.id}",
                                title=o.title,
                                description=o.description,
                            )
                            for o in step.options
                        ]
                    )
                ],
            ),
        )
    else:
        hint = "\n\n_(send *skip* to leave blank, *cancel* to stop)_" if step.optional else "\n\n_(send *cancel* to stop)_"
        await send_text_reply(http, phone_number_id, wa_id, body + hint)


async def start_form(
    store: Store, http: httpx.AsyncClient, phone_number_id: str, wa_id: str, form_id: str
) -> bool:
    form = FORMS.get(form_id)
    if form is None:
        return False
    await store.save_form_session(FormSession(wa_id=wa_id, form_id=form_id, step=0))
    await _send_step(http, phone_number_id, wa_id, form, 0)
    return True


def _brief_prompt(form: Form, answers: dict[str, str]) -> str:
    lines = [f"{k}: {v}" for k, v in answers.items()]
    return f"{form.completion_instruction}\n\nForm answers:\n" + "\n".join(lines)


FORM_TO_CARD = {
    "industry": "category",
    "audience": "audience",
    "difference": "difference",
    "touchpoints": "touchpoints",
    "personality": "personality",
    "avoid": "avoid",
    "style": "style",
    "colors": "colors",
}


async def _save_to_brand(store: Store, wa_id: str, answers: dict[str, str]) -> None:
    """Completed brief becomes the brand's memory card (new brand if the name differs from the active one)."""
    name = answers.get("brand_name", "").strip()
    brand = await store.active_brand(wa_id)
    if name and brand.name not in (DEFAULT_BRAND_NAME, name) and name.lower() not in brand.name.lower():
        brand = await store.create_brand(wa_id, name)
    patch = {card: answers[key] for key, card in FORM_TO_CARD.items() if answers.get(key)}
    await store.update_brand(brand.id, name or None, patch)


async def handle_incoming(
    store: Store,
    http: httpx.AsyncClient,
    phone_number_id: str,
    wa_id: str,
    kind: Literal["text", "button", "list"],
    value: str,
    title: str = "",
) -> Completed | bool:
    """Route an incoming message through the active form.

    Returns False when no form is active (or the message is not for the form), True when the form
    consumed the message, and Completed when the last step was answered.
    """
    session = await store.get_form_session(wa_id)
    if session is None:
        return False
    form = FORMS.get(session.form_id)
    if form is None or session.step >= len(form.steps):
        await store.clear_form_session(wa_id)
        return False
    step = form.steps[session.step]

    if kind == "text" and (is_new_session_command(value) or is_wrap_command(value)):
        return False
    if kind == "text" and value.strip().lower() in CANCEL_WORDS:
        await store.clear_form_session(wa_id)
        await send_text_reply(http, phone_number_id, wa_id, "Okay, cancelled. Tell me whenever you want to pick it up again.")
        return True

    answer: str | None = None
    if step.kind == "text":
        if kind != "text":
            return False  # stale button/list tap: let the agent handle it
        text = value.strip()
        if step.optional and text.lower() in SKIP_WORDS:
            answer = ""
        elif text:
            answer = text
    else:
        if kind == "text":
            option = _match_option(step, value)
            if option is not None:
                answer = option.title  # typed the option instead of tapping it
            else:
                nudges = int(session.answers.get("_nudges", "0")) + 1
                if nudges > MAX_NUDGES:
                    await store.clear_form_session(wa_id)  # don't trap the user; the agent takes over
                    return False
                session.answers["_nudges"] = str(nudges)
                await store.save_form_session(session)
                await send_text_reply(
                    http, phone_number_id, wa_id, "Tap one of the options below, or type *cancel* to stop the questions."
                )
                await _send_step(http, phone_number_id, wa_id, form, session.step)
                return True
        else:
            prefix = f"{ID_PREFIX}{step.key}:"
            if not value.startswith(prefix):
                return False  # tap from an unrelated message
            answer = title or value.removeprefix(prefix)

    if answer is None:
        await send_text_reply(http, phone_number_id, wa_id, "I didn't catch that - please send a text answer.")
        return True

    session.answers.pop("_nudges", None)
    if answer:
        session.answers[step.key] = answer
    session.step += 1
    if session.step >= len(form.steps):
        await store.save_submission(wa_id, form.id, session.answers)
        await store.clear_form_session(wa_id)
        await _save_to_brand(store, wa_id, session.answers)
        return Completed(prompt=_brief_prompt(form, session.answers))
    await store.save_form_session(session)
    await _send_step(http, phone_number_id, wa_id, form, session.step)
    return True

"""Slack Block Kit payload shapes for interactive messages (validated)."""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, model_validator

MAX_INTERACTIVE_BODY = 3000
MAX_BUTTONS = 5
MAX_MENU_OPTIONS = 10
MAX_BUTTON_TEXT = 75
MAX_OPTION_TEXT = 75


class SlackButton(BaseModel):
    model_config = {"extra": "forbid"}

    action_id: str = Field(..., max_length=255, description="Developer-defined id for the button tap.")
    text: str = Field(..., max_length=MAX_BUTTON_TEXT, description="Button label shown to the user.")
    value: str | None = Field(None, max_length=2000, description="Optional value sent back on tap.")


class InteractiveButtonsPayload(BaseModel):
    model_config = {"extra": "forbid"}

    body_text: str = Field(..., max_length=MAX_INTERACTIVE_BODY)
    buttons: Annotated[list[SlackButton], Field(min_length=1, max_length=MAX_BUTTONS)]

    @model_validator(mode="after")
    def unique_action_ids(self) -> Self:
        seen: set[str] = set()
        for button in self.buttons:
            if button.action_id in seen:
                raise ValueError(f"Duplicate button action_id: {button.action_id!r}")
            seen.add(button.action_id)
        return self


class MenuOption(BaseModel):
    model_config = {"extra": "forbid"}

    value: str = Field(..., max_length=75)
    text: str = Field(..., max_length=MAX_OPTION_TEXT)
    description: str | None = Field(None, max_length=75)


class InteractiveMenuPayload(BaseModel):
    model_config = {"extra": "forbid"}

    body_text: str = Field(..., max_length=MAX_INTERACTIVE_BODY)
    action_id: str = Field(
        ...,
        max_length=255,
        description="Developer-defined id for the select menu.",
    )
    placeholder: str = Field(
        ...,
        max_length=150,
        description="Placeholder shown on the menu (e.g. 'Choose option').",
    )
    options: Annotated[list[MenuOption], Field(min_length=1, max_length=MAX_MENU_OPTIONS)]

    @model_validator(mode="after")
    def unique_option_values(self) -> Self:
        seen: set[str] = set()
        for option in self.options:
            if option.value in seen:
                raise ValueError(f"Duplicate menu option value: {option.value!r}")
            seen.add(option.value)
        return self


def buttons_to_blocks(payload: InteractiveButtonsPayload) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for button in payload.buttons:
        elem: dict[str, Any] = {
            "type": "button",
            "action_id": button.action_id,
            "text": {"type": "plain_text", "text": button.text, "emoji": True},
        }
        if button.value is not None:
            elem["value"] = button.value
        elements.append(elem)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": payload.body_text}},
        {"type": "actions", "elements": elements},
    ]


def menu_to_blocks(payload: InteractiveMenuPayload) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for option in payload.options:
        opt: dict[str, Any] = {
            "text": {"type": "plain_text", "text": option.text, "emoji": True},
            "value": option.value,
        }
        if option.description:
            opt["description"] = {
                "type": "plain_text",
                "text": option.description,
                "emoji": True,
            }
        options.append(opt)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": payload.body_text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "static_select",
                    "action_id": payload.action_id,
                    "placeholder": {
                        "type": "plain_text",
                        "text": payload.placeholder,
                        "emoji": True,
                    },
                    "options": options,
                }
            ],
        },
    ]

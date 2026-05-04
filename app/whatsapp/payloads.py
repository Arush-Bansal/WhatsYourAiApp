"""WhatsApp Cloud API payload shapes for interactive messages (validated)."""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

# https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-list-messages
MAX_LIST_ROWS_TOTAL = 10
MAX_INTERACTIVE_BODY = 1024
MAX_BUTTONS = 3


class ReplyButton(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(..., max_length=256, description="Developer-defined id for the button tap.")
    title: str = Field(..., max_length=20, description="Button label shown to the user.")


class InteractiveButtonsPayload(BaseModel):
    model_config = {"extra": "forbid"}

    body_text: str = Field(..., max_length=MAX_INTERACTIVE_BODY)
    buttons: Annotated[list[ReplyButton], Field(min_length=1, max_length=MAX_BUTTONS)]


class ListRow(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(..., max_length=200)
    title: str = Field(..., max_length=24)
    description: str | None = Field(None, max_length=72)


class ListSection(BaseModel):
    model_config = {"extra": "forbid"}

    title: str | None = Field(None, max_length=24)
    rows: Annotated[list[ListRow], Field(min_length=1)]


class InteractiveListPayload(BaseModel):
    model_config = {"extra": "forbid"}

    body_text: str = Field(..., max_length=MAX_INTERACTIVE_BODY)
    button_label: str = Field(
        ...,
        max_length=20,
        description="Label on the sheet opener (e.g. 'Choose option').",
    )
    sections: Annotated[list[ListSection], Field(min_length=1)]

    @model_validator(mode="after")
    def cap_rows_and_unique_ids(self) -> Self:
        total = sum(len(s.rows) for s in self.sections)
        if total > MAX_LIST_ROWS_TOTAL:
            raise ValueError(
                f"WhatsApp allows at most {MAX_LIST_ROWS_TOTAL} list rows total; got {total}."
            )
        seen: set[str] = set()
        for section in self.sections:
            for row in section.rows:
                if row.id in seen:
                    raise ValueError(f"Duplicate list row id: {row.id!r}")
                seen.add(row.id)
        return self


def demo_interactive_buttons_payload() -> InteractiveButtonsPayload:
    """Default demo layout (previously hardcoded in the client)."""
    return InteractiveButtonsPayload(
        body_text="Tap a button - demo reply.",
        buttons=[
            ReplyButton(id="demo_ok", title="Sounds good"),
            ReplyButton(id="demo_later", title="Not now"),
            ReplyButton(id="demo_info", title="More info"),
        ],
    )


def demo_interactive_list_payload() -> InteractiveListPayload:
    """Default demo layout (previously hardcoded in the client)."""
    return InteractiveListPayload(
        body_text="Open the list and pick one option.",
        button_label="Choose option",
        sections=[
            ListSection(
                title="Topics",
                rows=[
                    ListRow(
                        id="list_billing",
                        title="Billing",
                        description="Invoices and payments",
                    ),
                    ListRow(
                        id="list_support",
                        title="Support",
                        description="Help with the product",
                    ),
                    ListRow(
                        id="list_feedback",
                        title="Feedback",
                        description="Ideas and issues",
                    ),
                ],
            ),
            ListSection(
                title="Priority",
                rows=[
                    ListRow(
                        id="list_urgent",
                        title="Urgent",
                        description="Needs a fast reply",
                    ),
                    ListRow(
                        id="list_normal",
                        title="Normal",
                        description="Whenever you can",
                    ),
                ],
            ),
        ],
    )

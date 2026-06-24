"""Gmail reply payload shapes and RFC 2822 message construction."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import parseaddr

from pydantic import BaseModel, Field

MAX_BODY_TEXT = 100_000


class GmailReplyPayload(BaseModel):
    model_config = {"extra": "forbid"}

    body_text: str = Field(..., max_length=MAX_BODY_TEXT)
    body_html: str | None = Field(None, max_length=MAX_BODY_TEXT)
    subject: str | None = Field(
        None,
        max_length=998,
        description="Reply subject; defaults to Re: original subject when omitted.",
    )


def _reply_subject(original_subject: str, override: str | None) -> str:
    if override:
        return override
    subject = original_subject.strip()
    if subject.lower().startswith("re:"):
        return subject
    return f"Re: {subject}" if subject else "Re:"


def build_reply_raw(
    *,
    to_email: str,
    from_email: str,
    subject: str,
    thread_id: str,
    in_reply_to: str,
    references: str,
    payload: GmailReplyPayload,
) -> str:
    """Build a base64url-encoded RFC 2822 message for Gmail API messages.send."""
    msg = EmailMessage()
    msg["To"] = to_email
    msg["From"] = from_email
    msg["Subject"] = _reply_subject(subject, payload.subject)
    msg["In-Reply-To"] = in_reply_to
    msg["References"] = references

    if payload.body_html:
        msg.set_content(payload.body_text)
        msg.add_alternative(payload.body_html, subtype="html")
    else:
        msg.set_content(payload.body_text)

    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


def extract_email_address(header_value: str) -> str:
    """Return the bare email address from a From/To header."""
    _name, addr = parseaddr(header_value)
    return addr.lower()

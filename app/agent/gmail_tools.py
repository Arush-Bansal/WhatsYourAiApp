from __future__ import annotations

from agents import RunContextWrapper, function_tool

from app.agent.context import GmailAgentContext
from app.gmail.client import send_reply
from app.gmail.payloads import GmailReplyPayload


@function_tool
async def send_gmail_reply(
    wrapper: RunContextWrapper[GmailAgentContext],
    payload: GmailReplyPayload,
) -> str:
    """Send a reply email in the current thread."""
    c = wrapper.context
    in_reply_to = c.message_id_header or c.message_id
    references = c.references or in_reply_to
    ok = await send_reply(
        c.http,
        to_email=c.from_email,
        thread_id=c.thread_id,
        subject=c.subject,
        in_reply_to=in_reply_to,
        references=references,
        payload=payload,
    )
    return "ok:reply_sent" if ok else "error:reply_not_sent"

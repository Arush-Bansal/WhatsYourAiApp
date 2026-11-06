from __future__ import annotations

import logging
import os
from typing import Any

from agents import Runner

from app.agent.agent import create_gmail_agent, create_slack_agent, create_whatsapp_agent
from app.agent.context import GmailAgentContext, SlackAgentContext, WhatsAppAgentContext
from app.config import OPENAI_AGENT_MODEL, OPENAI_API_KEY
from app.memory import prepare_turn

logger = logging.getLogger(__name__)

MAX_STORED_CHARS = 1500


async def run_whatsapp_turn(
    *,
    context: WhatsAppAgentContext,
    user_prompt: str,
    attachments: list[dict[str, Any]] | None = None,
) -> Any | None:
    """Run the WhatsApp agent for one inbound user turn. Returns the SDK RunResult or None if skipped."""
    if not (OPENAI_API_KEY or "").strip():
        logger.error("OPENAI_API_KEY is not set; skipping agent run")
        return None

    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY.strip()

    store = context.store
    memory_block = ""
    history: list[dict[str, str]] = []
    if store is not None:
        turn = await prepare_turn(store, context.to_wa_id)
        context.session_id = turn.session.id
        context.brand_id = turn.brand.id
        memory_block, history = turn.memory_block, turn.history
        await store.append_message(context.to_wa_id, "user", user_prompt[:MAX_STORED_CHARS], turn.session.id)

    content: Any = user_prompt
    if attachments:
        content = [{"type": "input_text", "text": user_prompt}, *attachments]

    agent = create_whatsapp_agent(model=OPENAI_AGENT_MODEL)
    result = await Runner.run(
        starting_agent=agent,
        input=[
            *([{"role": "system", "content": memory_block}] if memory_block else []),
            *history,
            {"role": "user", "content": content},
        ],
        context=context,
    )
    logger.info(
        "WhatsApp agent run completed; final_output=%r",
        getattr(result, "final_output", None),
    )
    return result


async def run_slack_turn(
    *,
    context: SlackAgentContext,
    user_prompt: str,
) -> Any | None:
    """Run the Slack agent for one inbound user turn. Returns the SDK RunResult or None if skipped."""
    if not (OPENAI_API_KEY or "").strip():
        logger.error("OPENAI_API_KEY is not set; skipping agent run")
        return None

    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY.strip()

    agent = create_slack_agent(model=OPENAI_AGENT_MODEL, business=context.business)
    result = await Runner.run(
        starting_agent=agent,
        input=user_prompt,
        context=context,
    )
    logger.info(
        "Slack agent run completed; final_output=%r",
        getattr(result, "final_output", None),
    )
    return result


async def run_gmail_turn(
    *,
    context: GmailAgentContext,
    user_prompt: str,
) -> Any | None:
    """Run the Gmail agent for one inbound user turn. Returns the SDK RunResult or None if skipped."""
    if not (OPENAI_API_KEY or "").strip():
        logger.error("OPENAI_API_KEY is not set; skipping agent run")
        return None

    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY.strip()

    agent = create_gmail_agent(model=OPENAI_AGENT_MODEL, business=context.business)
    result = await Runner.run(
        starting_agent=agent,
        input=user_prompt,
        context=context,
    )
    logger.info(
        "Gmail agent run completed; final_output=%r",
        getattr(result, "final_output", None),
    )
    return result

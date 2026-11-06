from __future__ import annotations

import logging
import os
from typing import Any

from agents import Runner

from app.agent.agent import create_gmail_agent, create_slack_agent, create_whatsapp_agent
from app.agent.context import GmailAgentContext, SlackAgentContext, WhatsAppAgentContext
from app.config import OPENAI_AGENT_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)

HISTORY_TURNS = 12  # recent messages (user + assistant) replayed to the model
MAX_STORED_CHARS = 1500


async def run_whatsapp_turn(
    *,
    context: WhatsAppAgentContext,
    user_prompt: str,
) -> Any | None:
    """Run the WhatsApp agent for one inbound user turn. Returns the SDK RunResult or None if skipped."""
    if not (OPENAI_API_KEY or "").strip():
        logger.error("OPENAI_API_KEY is not set; skipping agent run")
        return None

    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY.strip()

    store = context.store
    history: list[dict[str, str]] = []
    if store is not None:
        history = await store.recent_messages(context.to_wa_id, HISTORY_TURNS)
        await store.append_message(context.to_wa_id, "user", user_prompt[:MAX_STORED_CHARS])

    agent = create_whatsapp_agent(model=OPENAI_AGENT_MODEL)
    result = await Runner.run(
        starting_agent=agent,
        input=[*history, {"role": "user", "content": user_prompt}],
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

from __future__ import annotations

import logging
import os
from typing import Any

from agents import Runner

from app.agent.agent import create_whatsapp_agent
from app.agent.context import WhatsAppAgentContext
from app.config import OPENAI_AGENT_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)


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

    agent = create_whatsapp_agent(model=OPENAI_AGENT_MODEL)
    result = await Runner.run(
        starting_agent=agent,
        input=user_prompt,
        context=context,
    )
    logger.info(
        "WhatsApp agent run completed; final_output=%r",
        getattr(result, "final_output", None),
    )
    return result

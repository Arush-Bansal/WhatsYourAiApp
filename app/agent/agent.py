from agents import Agent

from app.agent.context import WhatsAppAgentContext
from app.agent.tools import (
    send_whatsapp_interactive_buttons,
    send_whatsapp_interactive_list,
    send_whatsapp_text,
)

WHATSAPP_AGENT_INSTRUCTIONS = """You are a helpful assistant for a WhatsApp Business chatbot.
Users only see content you send via the provided WhatsApp tools, not your raw assistant text.
Respond by calling one or more of the send_whatsapp_* tools.
Prefer a single clear reply when that is enough.
Use send_whatsapp_interactive_buttons when up to three short choices are appropriate.
Use send_whatsapp_interactive_list for larger menus (respect the schema: at most 10 rows in total).
Follow the character limits enforced by each tool's parameters."""


def create_whatsapp_agent(*, model: str) -> Agent[WhatsAppAgentContext]:
    return Agent[WhatsAppAgentContext](
        name="WhatsApp assistant",
        instructions=WHATSAPP_AGENT_INSTRUCTIONS,
        model=model,
        tools=[
            send_whatsapp_text,
            send_whatsapp_interactive_buttons,
            send_whatsapp_interactive_list,
        ],
    )

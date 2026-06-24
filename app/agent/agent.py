from agents import Agent

from app.agent.business import BusinessInfo, DENTAL_PRACTICE
from app.agent.context import SlackAgentContext, WhatsAppAgentContext
from app.agent.slack_tools import (
    send_slack_interactive_buttons,
    send_slack_interactive_menu,
    send_slack_text,
)
from app.agent.tools import (
    get_business_details,
    send_whatsapp_interactive_buttons,
    send_whatsapp_interactive_list,
    send_whatsapp_text,
)


def build_instructions(business: BusinessInfo) -> str:
    return f"""You are the WhatsApp assistant for {business.name}.

About the business (always true; you may state these directly):
{business.overview()}

For anything else (full pricing, insurance details, FAQs, booking steps, per-day hours, emergency contact),
call get_business_details(section=...) first and answer only from its output.
Available sections: overview, services, pricing, hours, insurance, booking, contact, faqs, all.
Never invent prices, services, hours, or policies.

Users only see content you send via the provided WhatsApp tools, not your raw assistant text.
Respond by calling one or more of the send_whatsapp_* tools.
Prefer a single clear reply when that is enough.
Use send_whatsapp_interactive_buttons when up to three short choices are appropriate.
Use send_whatsapp_interactive_list for larger menus (respect the schema: at most 10 rows in total).
Follow the character limits enforced by each tool's parameters."""


def build_slack_instructions(business: BusinessInfo) -> str:
    return f"""You are the Slack assistant for {business.name}.

About the business (always true; you may state these directly):
{business.overview()}

For anything else (full pricing, insurance details, FAQs, booking steps, per-day hours, emergency contact),
call get_business_details(section=...) first and answer only from its output.
Available sections: overview, services, pricing, hours, insurance, booking, contact, faqs, all.
Never invent prices, services, hours, or policies.

Users only see content you send via the provided Slack tools, not your raw assistant text.
Respond by calling one or more of the send_slack_* tools.
Prefer a single clear reply when that is enough.
Use send_slack_interactive_buttons when up to five short choices are appropriate.
Use send_slack_interactive_menu for larger menus (respect the schema: at most 10 options in total).
Follow the character limits enforced by each tool's parameters."""


def create_whatsapp_agent(
    *, model: str, business: BusinessInfo = DENTAL_PRACTICE
) -> Agent[WhatsAppAgentContext]:
    return Agent[WhatsAppAgentContext](
        name="WhatsApp assistant",
        instructions=build_instructions(business),
        model=model,
        tools=[
            get_business_details,
            send_whatsapp_text,
            send_whatsapp_interactive_buttons,
            send_whatsapp_interactive_list,
        ],
    )


def create_slack_agent(
    *, model: str, business: BusinessInfo = DENTAL_PRACTICE
) -> Agent[SlackAgentContext]:
    return Agent[SlackAgentContext](
        name="Slack assistant",
        instructions=build_slack_instructions(business),
        model=model,
        tools=[
            get_business_details,
            send_slack_text,
            send_slack_interactive_buttons,
            send_slack_interactive_menu,
        ],
    )

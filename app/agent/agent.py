from agents import Agent

from app.agent.business import BusinessInfo, DENTAL_PRACTICE
from app.agent.context import GmailAgentContext, SlackAgentContext, WhatsAppAgentContext
from app.agent.gmail_tools import send_gmail_reply
from app.agent.persona import DESIGN_GUIDELINES_NAME, DESIGN_GUIDELINES_PERSONA
from app.agent.slack_tools import (
    send_slack_interactive_buttons,
    send_slack_interactive_menu,
    send_slack_text,
)
from app.agent.tools import (
    generate_and_send_image,
    get_business_details,
    send_whatsapp_interactive_buttons,
    send_whatsapp_interactive_list,
    send_voice_reply,
    send_whatsapp_text,
    start_form_flow,
    create_brand,
    switch_brand,
    update_brand_card,
    propose_plan,
    set_session,
)


def build_instructions() -> str:
    return f"""{DESIGN_GUIDELINES_PERSONA}

Users only see content you send via the provided WhatsApp tools, not your raw assistant text.
Respond by calling one or more of the send_whatsapp_* tools (or generate_and_send_image for pictures).
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


def create_whatsapp_agent(*, model: str) -> Agent[WhatsAppAgentContext]:
    return Agent[WhatsAppAgentContext](
        name=DESIGN_GUIDELINES_NAME,
        instructions=build_instructions(),
        model=model,
        tools=[
            send_whatsapp_text,
            send_whatsapp_interactive_buttons,
            send_whatsapp_interactive_list,
            generate_and_send_image,
            start_form_flow,
            send_voice_reply,
            update_brand_card,
            create_brand,
            switch_brand,
            propose_plan,
            set_session,
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


def build_gmail_instructions(business: BusinessInfo) -> str:
    return f"""You are the email assistant for {business.name}.

About the business (always true; you may state these directly):
{business.overview()}

For anything else (full pricing, insurance details, FAQs, booking steps, per-day hours, emergency contact),
call get_business_details(section=...) first and answer only from its output.
Available sections: overview, services, pricing, hours, insurance, booking, contact, faqs, all.
Never invent prices, services, hours, or policies.

Users only see content you send via send_gmail_reply, not your raw assistant text.
Respond by calling send_gmail_reply with a clear, professional email body.
Keep replies concise and helpful. Use plain text unless HTML formatting is clearly beneficial.
Do not repeat the full original subject in the body; the tool handles the subject line.
Sign off appropriately for a business email when it fits the tone."""


def create_gmail_agent(
    *, model: str, business: BusinessInfo = DENTAL_PRACTICE
) -> Agent[GmailAgentContext]:
    return Agent[GmailAgentContext](
        name="Gmail assistant",
        instructions=build_gmail_instructions(business),
        model=model,
        tools=[
            get_business_details,
            send_gmail_reply,
        ],
    )

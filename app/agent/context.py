from dataclasses import dataclass, field

import httpx

from app.agent.business import BusinessInfo, DENTAL_PRACTICE


@dataclass
class BaseAgentContext:
    """Shared per-run dependencies for business tools (not sent to the model)."""

    http: httpx.AsyncClient
    business: BusinessInfo = field(default_factory=lambda: DENTAL_PRACTICE)


@dataclass
class WhatsAppAgentContext(BaseAgentContext):
    """Per-run dependencies for WhatsApp send tools (not sent to the model)."""

    phone_number_id: str = ""
    to_wa_id: str = ""


@dataclass
class SlackAgentContext(BaseAgentContext):
    """Per-run dependencies for Slack send tools (not sent to the model)."""

    channel_id: str = ""
    user_id: str = ""

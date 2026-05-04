from dataclasses import dataclass, field

import httpx

from app.agent.business import BusinessInfo, DENTAL_PRACTICE


@dataclass
class WhatsAppAgentContext:
    """Per-run dependencies for WhatsApp send tools (not sent to the model)."""

    http: httpx.AsyncClient
    phone_number_id: str
    to_wa_id: str
    business: BusinessInfo = field(default_factory=lambda: DENTAL_PRACTICE)

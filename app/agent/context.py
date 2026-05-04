from dataclasses import dataclass

import httpx


@dataclass
class WhatsAppAgentContext:
    """Per-run dependencies for WhatsApp send tools (not sent to the model)."""

    http: httpx.AsyncClient
    phone_number_id: str
    to_wa_id: str

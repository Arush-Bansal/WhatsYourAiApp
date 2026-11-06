"""Text-to-speech via the OpenAI Audio API."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_TTS_MODEL, OPENAI_TTS_VOICE

logger = logging.getLogger(__name__)


async def synthesize_speech(text: str, style: str | None = None) -> bytes | None:
    """Return Ogg/Opus bytes (WhatsApp voice-note format), or None on failure."""
    key = (OPENAI_API_KEY or "").strip()
    if not key:
        logger.error("OPENAI_API_KEY is not set; cannot synthesize speech")
        return None
    client = AsyncOpenAI(api_key=key, timeout=120.0)
    try:
        resp = await client.audio.speech.create(
            model=OPENAI_TTS_MODEL,
            voice=OPENAI_TTS_VOICE,
            input=text[:3000],
            instructions=style or "Speak naturally and warmly, like a friendly designer on a voice note.",
            response_format="opus",
        )
        return resp.content
    except Exception:
        logger.exception("Speech synthesis failed (model=%s)", OPENAI_TTS_MODEL)
        return None

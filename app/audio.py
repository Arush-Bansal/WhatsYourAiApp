"""Text-to-speech via the OpenAI Audio API."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_TTS_MODEL, OPENAI_TTS_VOICE

logger = logging.getLogger(__name__)

NATURAL_STYLE = (
    "Sound like a warm, relaxed friend sending a quick voice note, not a narrator or assistant. "
    "Conversational pace with small natural pauses, varied intonation, a hint of a smile, and "
    "occasional casual fillers where they fit. Never announcer cadence, never read like a list. "
    "Hindi or Hinglish words should be pronounced the way a native Indian speaker would say them."
)


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
            instructions=NATURAL_STYLE + (f" Extra direction: {style}" if style else ""),
            response_format="opus",
        )
        return resp.content
    except Exception:
        logger.exception("Speech synthesis failed (model=%s)", OPENAI_TTS_MODEL)
        return None

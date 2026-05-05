from __future__ import annotations

import io
import logging

from openai import AsyncOpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_TRANSCRIPTION_MODEL,
    OPENAI_TRANSCRIPTION_ROMANIZE_MODEL,
)

logger = logging.getLogger(__name__)

_HINGLISH_SYSTEM = """You format voice-to-text transcripts for Indian WhatsApp users.
Rules:
- Preserve the same spoken meaning and wording; you may fix small obvious ASR errors only.
- Any Hindi (including text currently in Devanagari script) must be written in Roman letters (Latin script), natural informal Hinglish style.
- Do NOT translate Hindi into English; keep Hindi words, just in Roman script.
- Keep English words/phrases in English as spoken.
- Output only the formatted transcript, with no preamble or quotes."""


def _filename_suffix_from_mime(mime_type: str | None) -> str:
    if not mime_type:
        return ".ogg"
    m = mime_type.lower()
    if "ogg" in m or "opus" in m:
        return ".ogg"
    if "mpeg" in m or m.endswith("/mp3"):
        return ".mp3"
    if "mp4" in m or "m4a" in m:
        return ".m4a"
    if "wav" in m:
        return ".wav"
    if "webm" in m:
        return ".webm"
    return ".ogg"


async def transcribe_voice_to_hinglish(
    audio_bytes: bytes,
    mime_type: str | None,
) -> str | None:
    """Transcribe audio with OpenAI, then normalize to Hinglish (Roman Hindi). Returns None on failure."""
    key = (OPENAI_API_KEY or "").strip()
    if not key:
        logger.error("OPENAI_API_KEY is not set; cannot transcribe voice")
        return None

    client = AsyncOpenAI(api_key=key)
    suffix = _filename_suffix_from_mime(mime_type)
    buf = io.BytesIO(audio_bytes)
    buf.name = f"voice{suffix}"

    try:
        tr = await client.audio.transcriptions.create(
            file=buf,
            model=OPENAI_TRANSCRIPTION_MODEL,
        )
    except Exception:
        logger.exception("OpenAI transcription failed")
        return None

    raw = (getattr(tr, "text", None) or "").strip()
    if not raw:
        logger.warning("OpenAI transcription returned empty text")
        return None

    try:
        roman = await client.chat.completions.create(
            model=OPENAI_TRANSCRIPTION_ROMANIZE_MODEL,
            messages=[
                {"role": "system", "content": _HINGLISH_SYSTEM},
                {"role": "user", "content": raw},
            ],
            temperature=0.2,
        )
    except Exception:
        logger.exception("OpenAI Hinglish normalization failed")
        return None

    choice = roman.choices[0].message.content
    out = (choice or "").strip()
    if not out:
        logger.warning("Hinglish normalization returned empty; using raw transcript")
        return raw
    return out

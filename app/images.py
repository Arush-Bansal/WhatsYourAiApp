"""Image generation via the OpenAI Images API."""

from __future__ import annotations

import base64
import logging

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_IMAGE_MODEL

logger = logging.getLogger(__name__)


async def generate_image(prompt: str, size: str = "1024x1024") -> bytes | None:
    """Return JPEG bytes for prompt, or None on failure."""
    key = (OPENAI_API_KEY or "").strip()
    if not key:
        logger.error("OPENAI_API_KEY is not set; cannot generate image")
        return None
    client = AsyncOpenAI(api_key=key, timeout=180.0)
    try:
        resp = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=size,
            output_format="jpeg",
        )
    except Exception:
        logger.exception("Image generation failed (model=%s)", OPENAI_IMAGE_MODEL)
        return None
    b64 = resp.data[0].b64_json if resp.data else None
    if not b64:
        logger.error("Image generation returned no image data")
        return None
    return base64.b64decode(b64)

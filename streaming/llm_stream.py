"""OpenAI token streaming for voice pipeline."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from config import (
    OPENAI_API_KEY,
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_MODEL,
    OPENAI_VOICE_TEMPERATURE,
)

logger = logging.getLogger(__name__)


async def stream_chat_tokens(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> AsyncIterator[str]:
    temp = OPENAI_VOICE_TEMPERATURE if temperature is None else temperature
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY is not configured.')
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    limit = max_tokens or OPENAI_MAX_COMPLETION_TOKENS
    kwargs: dict = {
        'model': OPENAI_MODEL,
        'messages': messages,
        'temperature': temp,
        'stream': True,
    }
    try:
        stream = await client.chat.completions.create(
            **kwargs,
            max_completion_tokens=limit,
        )
    except Exception as exc:
        if 'max_completion_tokens' not in str(exc).lower():
            raise
        stream = await client.chat.completions.create(
            **kwargs,
            max_tokens=limit,
        )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta

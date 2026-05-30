"""Async OpenAI LLM streaming with phrase-level chunking for TTS."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator

from config import (
    OPENAI_API_KEY,
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_MODEL,
    OPENAI_VOICE_TEMPERATURE,
    STREAM_LLM_MIN_WORDS,
    STREAM_LLM_NEXT_MIN_WORDS,
)

logger = logging.getLogger(__name__)

_STRIP_MARKDOWN = re.compile(r'[*_~`]')
_PUNCT_FLUSH = re.compile(r'[,;:.!?।]')
_WORD = re.compile(r'\S+')


class PhraseBuffer:
    """Flush phrases to TTS immediately upon sentence completion marks."""

    def __init__(
        self,
        *,
        first_min_words: int = STREAM_LLM_MIN_WORDS,
        next_min_words: int = STREAM_LLM_NEXT_MIN_WORDS,
    ) -> None:
        self.buffer = ''

    def push(self, token: str) -> list[str]:
        self.buffer += token
        chunks: list[str] = []

        if '<' in self.buffer[-8:]:
            return chunks

        while True:
            match = re.search(r'[.,!?\n।]', self.buffer)
            if match:
                split_at = match.end()
                chunk = self.buffer[:split_at].strip()
                self.buffer = self.buffer[split_at:].lstrip()
                chunk = _STRIP_MARKDOWN.sub('', chunk)
                if chunk:
                    chunks.append(chunk)
            else:
                break
        return chunks

    def flush(self) -> str:
        chunk = self.buffer.strip()
        chunk = _STRIP_MARKDOWN.sub('', chunk)
        self.buffer = ''
        return chunk


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


async def complete_chat_message(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    """Non-streaming completion for script-correction retry."""
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
        'stream': False,
    }
    try:
        resp = await client.chat.completions.create(
            **kwargs,
            max_completion_tokens=limit,
        )
    except Exception as exc:
        if 'max_completion_tokens' not in str(exc).lower():
            raise
        resp = await client.chat.completions.create(
            **kwargs,
            max_tokens=limit,
        )
    return (resp.choices[0].message.content or '').strip()


def phrases_from_text(text: str) -> list[str]:
    """Split final assistant text into TTS phrase chunks."""
    splitter = PhraseBuffer()
    phrases: list[str] = []
    for part in text.split():
        phrases.extend(splitter.push(part + ' '))
    remainder = splitter.flush()
    if remainder:
        phrases.append(remainder)
    return phrases


class LlmWorker:
    """Streams GPT tokens and yields TTS-ready phrase chunks."""

    async def stream_phrases(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        splitter = PhraseBuffer()
        async for token in stream_chat_tokens(messages, temperature=temperature):
            if cancel_event and cancel_event.is_set():
                break
            for phrase in splitter.push(token):
                if cancel_event and cancel_event.is_set():
                    return
                yield phrase
        remainder = splitter.flush()
        if remainder and not (cancel_event and cancel_event.is_set()):
            yield remainder

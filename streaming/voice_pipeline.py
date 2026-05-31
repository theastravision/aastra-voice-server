"""
Async voice pipeline template — Audio → VAD → STT → LLM stream → TTS queue → output.

State locks (SessionStateMachine):
  - GREETING / STT_PROCESSING / LLM_STREAMING / TTS_PLAYING: PCM ignored for STT
  - is_greeted: greeting runs at most once per session
  - cancel_generation Event: barge-in stops LLM/TTS producers
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from config import F5_HINGLISH_SCRIPT, INTERJECTION_TIMEOUT_MS, OPENAI_VOICE_TEMPERATURE, is_indic_reply_script
from engines.interjections import pick_interjection
from engines.melo_phrase_buffer import HindiPhraseBuffer
from engines.tts_router import resolve_tts_backend
from llm_worker import PhraseBuffer, stream_chat_tokens
from streaming.session_state import SessionPhase, SessionStateMachine
from tts_worker import TtsWorker

logger = logging.getLogger(__name__)

SendJson = Callable[[str], Awaitable[None]]
SendBinary = Callable[[bytes], Awaitable[None]]
StreamTtsPhrase = Callable[[str, str], Awaitable[None]]
StreamInterjection = Callable[[object], Awaitable[None]]
CancelEvent = asyncio.Event


def _use_hindi_phrase_buffer(reply_script: str) -> bool:
    """Strong sentence boundaries for Indic TTS streaming (svara or F5 Devanagari)."""
    backend = resolve_tts_backend(reply_script)
    if backend == 'svara':
        return reply_script in ('hi', 'hinglish') or is_indic_reply_script(reply_script)
    if backend == 'melotts':
        return True
    return reply_script in ('hi', 'hinglish') and F5_HINGLISH_SCRIPT == 'devanagari'


class VoicePipeline:
    """LLM token stream → phrase queue → TTS consumer with state-aware locking."""

    def __init__(
        self,
        *,
        state: SessionStateMachine,
        tts: TtsWorker,
        duplex_cancel: CancelEvent,
        send_json: SendJson,
        stream_tts_phrase: StreamTtsPhrase,
        stream_interjection: StreamInterjection,
        evt: Callable[..., str],
    ) -> None:
        self._state = state
        self._tts = tts
        self._cancel = duplex_cancel
        self._send_json = send_json
        self._stream_tts_phrase = stream_tts_phrase
        self._stream_interjection = stream_interjection
        self._evt = evt

    async def run_llm_tts_turn(
        self,
        *,
        messages: list[dict[str, str]],
        tts_route: str,
        voice_id: str,
        reply_script: str = 'en',
    ) -> str:
        """
        Stream GPT tokens into PhraseBuffer; push sentences to TTS immediately.
        Returns full assistant text (may be truncated on barge-in).
        """
        await self._state.transition(SessionPhase.LLM_STREAMING)
        await self._tts.start(language_hint=tts_route, voice_id=voice_id)

        use_hindi_buffer = _use_hindi_phrase_buffer(reply_script)
        phrase_q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=8)
        first_token_event = asyncio.Event()
        first_phrase_event = asyncio.Event()
        full_reply: list[str] = []

        async def _llm_producer() -> None:
            splitter = HindiPhraseBuffer() if use_hindi_buffer else PhraseBuffer()
            try:
                async for token in stream_chat_tokens(
                    messages, temperature=OPENAI_VOICE_TEMPERATURE
                ):
                    if self._cancel.is_set():
                        break
                    if not first_token_event.is_set():
                        first_token_event.set()
                    full_reply.append(token)
                    await self._send_json(self._evt('assistant_delta', text=token))
                    for phrase in splitter.push(token):
                        if self._cancel.is_set():
                            break
                        if not first_phrase_event.is_set():
                            first_phrase_event.set()
                        await phrase_q.put(phrase)
                remainder = splitter.flush()
                if remainder and not self._cancel.is_set():
                    if not first_phrase_event.is_set():
                        first_phrase_event.set()
                    await phrase_q.put(remainder)
            finally:
                await phrase_q.put(None)

        async def _interjection_watcher() -> None:
            if use_hindi_buffer:
                return
            try:
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(first_token_event.wait()),
                        asyncio.create_task(first_phrase_event.wait()),
                    ],
                    timeout=INTERJECTION_TIMEOUT_MS / 1000.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if done:
                    return
                if self._cancel.is_set():
                    return
                clip = pick_interjection(reply_script)
                if clip is None:
                    return
                await self._stream_interjection(clip)
            except asyncio.CancelledError:
                raise

        async def _tts_consumer() -> None:
            await self._state.transition(SessionPhase.TTS_PLAYING)
            while True:
                phrase = await phrase_q.get()
                if phrase is None:
                    break
                if self._cancel.is_set():
                    while not phrase_q.empty():
                        phrase_q.get_nowait()
                    break
                await self._stream_tts_phrase(phrase, tts_route)

        if use_hindi_buffer:
            await asyncio.gather(_llm_producer(), _tts_consumer())
        else:
            await asyncio.gather(
                _interjection_watcher(),
                _llm_producer(),
                _tts_consumer(),
            )
        return ''.join(full_reply).strip()

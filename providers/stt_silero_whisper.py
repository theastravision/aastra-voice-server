"""Silero VAD + faster-whisper STT — speech gate, normalization, single flush."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from engines.audio_normalize import normalize_pcm_s16le
from engines.silero_vad import SileroVadGate
from providers.base import SttEvent, StreamingSTT
from stt_worker import SttWorker

logger = logging.getLogger(__name__)


class SileroWhisperSTT(StreamingSTT):
    """VAD-filtered PCM → SttWorker (one Whisper pass on flush)."""

    def __init__(
        self,
        *,
        on_utterance_end: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._worker = SttWorker()
        self._vad = SileroVadGate()
        self._on_utterance_end = on_utterance_end
        self._language_hint: str | None = None
        self._end_task: asyncio.Task | None = None

    async def start(self, *, language_hint: str | None = None) -> None:
        self._language_hint = language_hint
        self._vad.reset()
        await self._worker.start(language_hint=language_hint)

    async def close(self) -> None:
        if self._end_task and not self._end_task.done():
            self._end_task.cancel()
        await self._worker.close()

    async def push_pcm(self, chunk: bytes, **kwargs) -> list[SttEvent]:
        del kwargs
        gated, utterance_end = self._vad.push_pcm(chunk)
        events: list[SttEvent] = []
        if gated:
            normalized = normalize_pcm_s16le(gated)
            events.extend(await self._worker.push_pcm(normalized))
        if utterance_end and self._on_utterance_end is not None:
            self._schedule_utterance_end()
        return events

    async def flush(self) -> list[SttEvent]:
        gated, had_speech = self._vad.flush()
        if gated:
            normalized = normalize_pcm_s16le(gated)
            await self._worker.push_pcm(normalized)
        if not had_speech:
            return []
        return await self._worker.flush()

    def _schedule_utterance_end(self) -> None:
        if self._on_utterance_end is None:
            return
        if self._end_task and not self._end_task.done():
            return

        async def _fire() -> None:
            try:
                await self._on_utterance_end()
            except Exception:
                logger.exception('Silero VAD utterance_end callback failed')

        self._end_task = asyncio.create_task(_fire())

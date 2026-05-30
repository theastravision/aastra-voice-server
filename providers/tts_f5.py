"""F5-TTS streaming provider."""

from __future__ import annotations

from collections.abc import AsyncIterator

from providers.base import StreamingTTS, TtsAudioChunk
from tts_worker import TtsWorker


class F5StreamingTTS(StreamingTTS):
    def __init__(self) -> None:
        self._worker = TtsWorker()

    async def start(self, *, language_hint: str | None = None, voice_id: str | None = None) -> None:
        await self._worker.start(language_hint=language_hint, voice_id=voice_id)

    async def close(self) -> None:
        await self._worker.close()

    def synthesize_stream(self, text: str) -> AsyncIterator[TtsAudioChunk]:
        return self._worker.synthesize_stream(text)

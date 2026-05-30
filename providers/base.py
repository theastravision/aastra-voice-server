"""Provider protocols for streaming STT and TTS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class SttEvent:
    text: str
    is_final: bool
    language: str | None = None
    confidence: float | None = None


@dataclass
class TtsAudioChunk:
    pcm_s16le: bytes
    sample_rate: int


class StreamingSTT(ABC):
    """Push PCM chunks in; receive partial/final transcripts."""

    @abstractmethod
    async def start(self, *, language_hint: str | None = None) -> None:
        ...

    @abstractmethod
    async def push_pcm(self, chunk: bytes, *, rms_energy: float | None = None) -> list[SttEvent]:
        ...

    @abstractmethod
    async def flush(self) -> list[SttEvent]:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class StreamingTTS(ABC):
    """Stream synthesised audio for text fragments."""

    @abstractmethod
    async def start(self, *, language_hint: str | None = None) -> None:
        ...

    @abstractmethod
    def synthesize_stream(self, text: str) -> AsyncIterator[TtsAudioChunk]:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

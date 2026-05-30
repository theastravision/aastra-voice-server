"""Chunked faster-whisper STT for low-latency streaming (self-hosted)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from config import (
    STREAM_SAMPLE_RATE,
    STREAM_STT_MIN_CHARS,
    STREAM_STT_WINDOW_MS,
    STT_TRANSCRIBE_TIMEOUT_SECS,
    STT_UTTERANCE_MAX_SECS,
    WHISPER_BEAM_SIZE,
)
from engines.lang_detect import resolve_whisper_language
from engines.stt_filters import is_phantom_stt_text, pick_best_stt_text
from engines.whisper_stt import _build_transcribe_kwargs, get_model
from providers.base import SttEvent, StreamingSTT

logger = logging.getLogger(__name__)

_BYTES_PER_MS = STREAM_SAMPLE_RATE * 2 // 1000
_WINDOW_BYTES = _BYTES_PER_MS * STREAM_STT_WINDOW_MS
_MIN_FLUSH_BYTES = _BYTES_PER_MS * 800
_MAX_BUFFER_BYTES = _BYTES_PER_MS * STT_UTTERANCE_MAX_SECS * 1000


class WhisperChunkSTT(StreamingSTT):
    """Accumulate PCM windows; run Whisper in a thread pool on interval."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._language_hint: str | None = None
        self._last_partial = ''
        self._transcribe_lock = asyncio.Lock()

    async def start(self, *, language_hint: str | None = None) -> None:
        self._buffer.clear()
        self._language_hint = resolve_whisper_language(language_hint)
        self._last_partial = ''

    async def push_pcm(self, chunk: bytes, **kwargs) -> list[SttEvent]:
        del kwargs
        self._buffer.extend(chunk)
        if len(self._buffer) > _MAX_BUFFER_BYTES:
            drop = len(self._buffer) - _MAX_BUFFER_BYTES
            del self._buffer[:drop]
            logger.debug('STT buffer trimmed %d bytes (max %ss)', drop, STT_UTTERANCE_MAX_SECS)
        events: list[SttEvent] = []
        if len(self._buffer) >= _WINDOW_BYTES:
            events.extend(await self._transcribe_window(final=False))
        return events

    async def flush(self) -> list[SttEvent]:
        if len(self._buffer) < _MIN_FLUSH_BYTES:
            partial = self._last_partial.strip()
            self._buffer.clear()
            self._last_partial = ''
            if partial and not is_phantom_stt_text(partial):
                return [SttEvent(text=partial, is_final=True, language=None)]
            return []

        events = await self._transcribe_window(final=True)
        if events:
            return events

        partial = self._last_partial.strip()
        self._last_partial = ''
        best = pick_best_stt_text(partial)
        if best:
            return [SttEvent(text=best, is_final=True, language=None)]
        return []

    async def close(self) -> None:
        self._buffer.clear()
        self._last_partial = ''

    async def _transcribe_window(self, *, final: bool) -> list[SttEvent]:
        async with self._transcribe_lock:
            pcm = bytes(self._buffer)
            if final:
                self._buffer.clear()
            else:
                keep = min(len(self._buffer), _BYTES_PER_MS * 300)
                self._buffer = self._buffer[-keep:]

            if not pcm:
                return []

            loop = asyncio.get_running_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, self._run_whisper_sync, pcm),
                    timeout=STT_TRANSCRIBE_TIMEOUT_SECS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    'Whisper chunk transcribe timed out after %.0fs (final=%s)',
                    STT_TRANSCRIBE_TIMEOUT_SECS,
                    final,
                )
                if final:
                    partial = self._last_partial.strip()
                    best = pick_best_stt_text(partial)
                    if best:
                        return [SttEvent(text=best, is_final=True, language=None)]
                return []

            text = (result.get('text') or '').strip()
            if not text or text == self._last_partial:
                return []
            if is_phantom_stt_text(text):
                if final:
                    partial = self._last_partial.strip()
                    best = pick_best_stt_text(partial, text)
                    if best:
                        self._last_partial = ''
                        return [SttEvent(text=best, is_final=True, language=result.get('detected_language'))]
                    self._last_partial = ''
                return []
            if final and len(text) < STREAM_STT_MIN_CHARS:
                best = pick_best_stt_text(self._last_partial, text)
                if best:
                    self._last_partial = ''
                    return [SttEvent(text=best, is_final=True, language=result.get('detected_language'))]
                return []
            lang = result.get('detected_language')
            self._last_partial = text if not final else ''
            return [SttEvent(text=text, is_final=final, language=lang)]

    def _run_whisper_sync(self, pcm: bytes) -> dict:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(self._pcm_to_wav(pcm))
            wav_path = tmp.name
        try:
            model = get_model()
            lang = self._language_hint
            kwargs = _build_transcribe_kwargs(lang)
            if len(pcm) < _BYTES_PER_MS * 2000:
                kwargs = {**kwargs, 'vad_filter': False}
            segments, info = model.transcribe(wav_path, **kwargs)
            text = ''.join(seg.text for seg in segments).strip()
            detected = getattr(info, 'language', None) or lang or 'en'
            return {'text': text, 'detected_language': detected}
        finally:
            Path(wav_path).unlink(missing_ok=True)

    @staticmethod
    def _pcm_to_wav(pcm: bytes) -> bytes:
        import struct as st

        sr = STREAM_SAMPLE_RATE
        n = len(pcm)
        header = st.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + n,
            b'WAVE',
            b'fmt ',
            16,
            1,
            1,
            sr,
            sr * 2,
            2,
            16,
            b'data',
            n,
        )
        return header + pcm

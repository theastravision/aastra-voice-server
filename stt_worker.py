"""Low-latency Faster-Whisper STT — accumulate PCM until client end_utterance."""

from __future__ import annotations

import asyncio
import logging
import struct
import tempfile
from pathlib import Path

from config import (
    STT_MIN_SPEECH_MS,
    STT_TRANSCRIBE_TIMEOUT_SECS,
    STT_UTTERANCE_MAX_SECS,
    STREAM_SAMPLE_RATE,
    WHISPER_BEAM_SIZE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
    WHISPER_MODEL_PATH,
)
from engines.lang_detect import resolve_whisper_language
from engines.stt_filters import is_phantom_stt_text, pick_best_stt_text
from engines.stt_model_registry import resolve_whisper_path_for_language
from engines.whisper_stt import _build_transcribe_kwargs, _ensure_ld_library_path
from providers.base import SttEvent, StreamingSTT

logger = logging.getLogger(__name__)

_BYTES_PER_MS = STREAM_SAMPLE_RATE * 2 // 1000
_MAX_UTTERANCE_BYTES = _BYTES_PER_MS * STT_UTTERANCE_MAX_SECS * 1000


class FasterWhisperInferenceManager:
    """CTranslate2 Whisper in float16 on CUDA; caches models by checkpoint path."""

    _instances: dict[str, FasterWhisperInferenceManager] = {}

    def __init__(self, model_id: str) -> None:
        _ensure_ld_library_path()
        from faster_whisper import WhisperModel

        device = WHISPER_DEVICE
        if device == 'cuda':
            try:
                import torch

                if not torch.cuda.is_available():
                    logger.warning('CUDA unavailable; falling back to CPU for Whisper')
                    device = 'cpu'
            except ImportError:
                device = 'cpu'
        compute = WHISPER_COMPUTE_TYPE if device == 'cuda' else 'int8'
        logger.info(
            'Loading Whisper model=%s device=%s compute=%s beam=%s',
            model_id,
            device,
            compute,
            WHISPER_BEAM_SIZE,
        )
        self._model_id = model_id
        self._model = WhisperModel(model_id, device=device, compute_type=compute)

    @classmethod
    def for_language(cls, language_hint: str | None) -> FasterWhisperInferenceManager:
        finetuned = resolve_whisper_path_for_language(language_hint)
        if finetuned:
            key = finetuned
        elif WHISPER_MODEL_PATH and Path(WHISPER_MODEL_PATH).is_dir():
            key = WHISPER_MODEL_PATH
        else:
            key = WHISPER_MODEL
        if key not in cls._instances:
            cls._instances[key] = cls(key)
        return cls._instances[key]

    def transcribe_pcm(self, pcm: bytes, *, language_hint: str | None, final: bool) -> dict:
        del final
        if not pcm:
            return {'text': '', 'detected_language': None}
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(_pcm_to_wav(pcm))
            wav_path = tmp.name
        try:
            lang = resolve_whisper_language(language_hint)
            kwargs = {**_build_transcribe_kwargs(lang), 'vad_filter': False}
            segments, info = self._model.transcribe(wav_path, **kwargs)
            text = ''.join(seg.text for seg in segments).strip()
            detected = getattr(info, 'language', None) or lang
            return {'text': text, 'detected_language': detected}
        finally:
            Path(wav_path).unlink(missing_ok=True)


def _pcm_to_wav(pcm: bytes) -> bytes:
    sr = STREAM_SAMPLE_RATE
    n = len(pcm)
    header = struct.pack(
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


class SttWorker(StreamingSTT):
    """Accumulate full utterance PCM; transcribe once on flush (no server-side VAD)."""

    def __init__(self) -> None:
        self._manager: FasterWhisperInferenceManager | None = None
        self._utterance_buffer = bytearray()
        self._language_hint: str | None = None
        self._last_detected_lang: str | None = None

    async def start(self, *, language_hint: str | None = None) -> None:
        self._reset_utterance()
        self._language_hint = language_hint
        self._manager = FasterWhisperInferenceManager.for_language(language_hint)

    async def close(self) -> None:
        self._reset_utterance()

    def _reset_utterance(self) -> None:
        self._utterance_buffer.clear()
        self._last_detected_lang = None

    async def push_pcm(self, chunk: bytes, *, rms_energy: float | None = None) -> list[SttEvent]:
        del rms_energy
        self._utterance_buffer.extend(chunk)
        if len(self._utterance_buffer) > _MAX_UTTERANCE_BYTES:
            drop = len(self._utterance_buffer) - _MAX_UTTERANCE_BYTES
            del self._utterance_buffer[:drop]
            logger.debug('STT utterance trimmed %d bytes (max %ss)', drop, STT_UTTERANCE_MAX_SECS)
        return []

    async def flush(self) -> list[SttEvent]:
        """Transcribe the full utterance buffer collected since the last flush."""
        utterance_pcm = bytes(self._utterance_buffer)
        min_bytes = _BYTES_PER_MS * STT_MIN_SPEECH_MS
        detected_lang = self._last_detected_lang
        final_text = ''

        if len(utterance_pcm) >= min_bytes:
            loop = asyncio.get_running_loop()
            if self._manager is None:
                self._manager = FasterWhisperInferenceManager.for_language(self._language_hint)
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self._manager.transcribe_pcm(
                            utterance_pcm, language_hint=self._language_hint, final=True
                        ),
                    ),
                    timeout=STT_TRANSCRIBE_TIMEOUT_SECS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    'Whisper utterance transcribe timed out after %.0fs',
                    STT_TRANSCRIBE_TIMEOUT_SECS,
                )
                self._reset_utterance()
                return []
            transcribed = (result.get('text') or '').strip()
            if result.get('detected_language'):
                detected_lang = result.get('detected_language')
            if transcribed and not is_phantom_stt_text(transcribed):
                final_text = transcribed
            elif transcribed:
                best = pick_best_stt_text(transcribed)
                if best:
                    final_text = best

        self._reset_utterance()

        if not final_text:
            return []

        return [
            SttEvent(
                text=final_text,
                is_final=True,
                language=detected_lang,
            )
        ]

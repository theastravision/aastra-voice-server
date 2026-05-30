"""Silero VAD — lightweight speech gate before Whisper STT."""

from __future__ import annotations

import logging
from threading import Lock

import numpy as np

from config import (
    SILERO_VAD_THRESHOLD,
    STT_SILENCE_END_MS,
    STREAM_SAMPLE_RATE,
)

logger = logging.getLogger(__name__)

# Silero expects 512 samples @ 16 kHz per frame (~32 ms).
_FRAME_SAMPLES = 512
_FRAME_BYTES = _FRAME_SAMPLES * 2

_model = None
_utils = None
_model_lock = Lock()


def _load_model():
    global _model, _utils
    if _model is not None:
        return _model, _utils
    with _model_lock:
        if _model is not None:
            return _model, _utils
        import torch

        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False,
            trust_repo=True,
        )
        _model = model
        _utils = utils
        logger.info('Silero VAD loaded')
        return _model, _utils


class SileroVadGate:
    """Accumulate speech-only PCM; detect end-of-utterance via silence timeout."""

    def __init__(
        self,
        *,
        sample_rate: int = STREAM_SAMPLE_RATE,
        silence_end_ms: int = STT_SILENCE_END_MS,
        threshold: float = SILERO_VAD_THRESHOLD,
    ) -> None:
        self.sample_rate = sample_rate
        self.silence_end_ms = silence_end_ms
        self.threshold = threshold
        self._carry = bytearray()
        self._speech_buffer = bytearray()
        self._in_speech = False
        self._silence_ms = 0
        self._speech_ms = 0
        self._model = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        model, _utils = _load_model()
        self._model = model

    def push_pcm(self, chunk: bytes) -> tuple[bytes, bool]:
        """
        Process PCM chunk.
        Returns (gated_speech_pcm_for_stt, utterance_end_detected).
        """
        if not chunk:
            return b'', False

        self._ensure_model()
        self._carry.extend(chunk)
        gated = bytearray()
        utterance_end = False
        frame_ms = int(_FRAME_SAMPLES * 1000 / self.sample_rate)

        while len(self._carry) >= _FRAME_BYTES:
            frame = bytes(self._carry[:_FRAME_BYTES])
            del self._carry[:_FRAME_BYTES]
            prob = self._speech_probability(frame)
            is_speech = prob >= self.threshold

            if is_speech:
                self._in_speech = True
                self._silence_ms = 0
                self._speech_ms += frame_ms
                self._speech_buffer.extend(frame)
                gated.extend(frame)
            elif self._in_speech:
                self._silence_ms += frame_ms
                self._speech_buffer.extend(frame)
                gated.extend(frame)
                if self._silence_ms >= self.silence_end_ms:
                    utterance_end = True
                    self._reset_utterance()

        return bytes(gated), utterance_end

    def flush(self) -> tuple[bytes, bool]:
        """Force end of current utterance if any speech was captured."""
        if self._in_speech and self._speech_ms > 0:
            pcm = bytes(self._speech_buffer)
            self._reset_utterance()
            return pcm, True
        self._reset_utterance()
        return b'', False

    def reset(self) -> None:
        self._carry.clear()
        self._reset_utterance()

    def _reset_utterance(self) -> None:
        self._speech_buffer.clear()
        self._in_speech = False
        self._silence_ms = 0
        self._speech_ms = 0

    def _speech_probability(self, frame_pcm: bytes) -> float:
        import torch

        samples = np.frombuffer(frame_pcm, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = torch.from_numpy(samples)
        with torch.no_grad():
            prob = self._model(tensor, self.sample_rate).item()
        return float(prob)


def warmup_silero_vad() -> None:
    """Load Silero VAD model in background warmup."""
    try:
        _load_model()
    except Exception:
        logger.exception('Silero VAD warmup failed')

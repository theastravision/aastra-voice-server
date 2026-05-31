"""Embedded svara-TTS inference for Indic languages (vLLM + SNAC)."""

from __future__ import annotations

from core.cuda_runtime import configure_cuda_runtime

configure_cuda_runtime()

import logging
import threading
from collections.abc import Iterator

from config import (
    SVARA_MODEL,
    SVARA_SNAC_DEVICE,
    SVARA_VLLM_GPU_MEMORY_UTILIZATION,
    SVARA_VLLM_MAX_MODEL_LEN,
    TTS_OUTPUT_FORMAT,
    _SVARA_VENDOR_DIR,
    resolve_svara_speaker,
)
from engines.tts_svara_pipeline import prepare_text_for_svara
from engines.tts_utils import ensure_pcm_s16le_bytes, pcm_s16le_to_wav, wav_to_mp3

logger = logging.getLogger(__name__)

_manager: 'SvaraTtsManager | None' = None
_manager_lock = threading.Lock()
_import_error: str | None = None
_warmup_error: str | None = None
_ready = False
SAMPLE_RATE = 24000


def svara_available() -> bool:
    global _import_error
    if _import_error is not None:
        return False
    if not _SVARA_VENDOR_DIR.is_dir():
        _import_error = (
            f'svara vendor missing: {_SVARA_VENDOR_DIR} (run scripts/install-svara-tts.sh)'
        )
        return False
    try:
        import vllm  # noqa: F401
        from tts_engine.orchestrator import SvaraTTSOrchestrator  # noqa: F401
        from tts_engine.transports import VLLMEmbeddedTransport  # noqa: F401

        return True
    except ImportError as exc:
        _import_error = str(exc)
        return False


def svara_ready() -> bool:
    return _ready


def svara_error() -> str | None:
    if _warmup_error:
        return _warmup_error
    if not svara_available():
        return _import_error
    return None


class SvaraTtsManager:
    """Singleton embedded svara orchestrator."""

    def __init__(self) -> None:
        from tts_engine.orchestrator import SvaraTTSOrchestrator
        from tts_engine.transports import VLLMEmbeddedTransport

        logger.info(
            'Initializing svara vLLM model=%s gpu_mem=%.2f',
            SVARA_MODEL,
            SVARA_VLLM_GPU_MEMORY_UTILIZATION,
        )
        VLLMEmbeddedTransport.initialize_engine(
            model=SVARA_MODEL,
            gpu_memory_utilization=SVARA_VLLM_GPU_MEMORY_UTILIZATION,
            max_model_len=SVARA_VLLM_MAX_MODEL_LEN,
        )
        transport = VLLMEmbeddedTransport(model=SVARA_MODEL)
        self._orchestrator = SvaraTTSOrchestrator(
            transport=transport,
            model=SVARA_MODEL,
            speaker_id=resolve_svara_speaker('hi'),
            device=SVARA_SNAC_DEVICE or None,
            prebuffer_seconds=0.5,
            concurrent_decode=True,
        )
        self._lock = threading.Lock()
        self._active_speaker = resolve_svara_speaker('hi')
        self._active_reply_script = 'hi'

    def set_active_speaker(
        self,
        *,
        reply_script: str | None = None,
        voice_id: str | None = None,
    ) -> None:
        script = (reply_script or self._active_reply_script or 'hi').lower()
        self._active_reply_script = script
        self._active_speaker = resolve_svara_speaker(script, voice_id)

    def warmup(self) -> None:
        self._orchestrator.warmup()

    def synthesize_stream_sync(
        self,
        text: str,
        *,
        reply_script: str | None = None,
        voice_id: str | None = None,
    ) -> Iterator[tuple[bytes, int]]:
        cleaned = (text or '').strip()
        if not cleaned:
            return

        script = (reply_script or self._active_reply_script or 'hi').lower()
        prepped = prepare_text_for_svara(cleaned, reply_script=script)  # type: ignore[arg-type]
        if not prepped.strip():
            return

        speaker = resolve_svara_speaker(script, voice_id) if voice_id else self._active_speaker
        with self._lock:
            for pcm_chunk in self._orchestrator.stream(
                prepped,
                speaker_id=speaker,
            ):
                if pcm_chunk:
                    yield ensure_pcm_s16le_bytes(pcm_chunk, sample_rate=SAMPLE_RATE), SAMPLE_RATE

    def synthesize_wav_bytes(
        self,
        text: str,
        *,
        reply_script: str | None = None,
        voice_id: str | None = None,
    ) -> tuple[bytes, str]:
        pcm = bytearray()
        for chunk, _sr in self.synthesize_stream_sync(
            text,
            reply_script=reply_script,
            voice_id=voice_id,
        ):
            pcm.extend(chunk)
        if not pcm:
            return b'', 'audio/wav'
        wav = pcm_s16le_to_wav(bytes(pcm), SAMPLE_RATE)
        if TTS_OUTPUT_FORMAT == 'mp3':
            return wav_to_mp3(wav), 'audio/mpeg'
        return wav, 'audio/wav'


def get_manager() -> SvaraTtsManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = SvaraTtsManager()
        return _manager


def warmup() -> None:
    global _ready, _warmup_error
    if not svara_available():
        _warmup_error = _import_error or 'svara not available'
        logger.warning('svara warmup skipped: %s', _warmup_error)
        return
    try:
        mgr = get_manager()
        mgr.warmup()
        _ready = True
        _warmup_error = None
        logger.info('svara-TTS warmup complete')
    except Exception as exc:
        _warmup_error = str(exc)
        _ready = False
        logger.exception('svara-TTS warmup failed')
        raise

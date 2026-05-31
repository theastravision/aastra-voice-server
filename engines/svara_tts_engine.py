"""HTTP client for svara-TTS sidecar (Kenpath API in separate .venv-svara)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator

import httpx

from config import (
    SVARA_MODEL,
    SVARA_TTS_TIMEOUT_SEC,
    SVARA_TTS_URL,
    TTS_OUTPUT_FORMAT,
    resolve_svara_speaker,
)
from engines.tts_svara_pipeline import prepare_text_for_svara
from engines.tts_utils import ensure_pcm_s16le_bytes, pcm_s16le_to_wav, wav_to_mp3

logger = logging.getLogger(__name__)

_manager: 'SvaraTtsManager | None' = None
_manager_lock = threading.Lock()
_availability_error: str | None = None
_warmup_error: str | None = None
_ready = False
_sidecar_ok = False
SAMPLE_RATE = 24000


def _base_url() -> str:
    return SVARA_TTS_URL.rstrip('/')


def _health_url() -> str:
    return f'{_base_url()}/health'


def _speech_url() -> str:
    return f'{_base_url()}/v1/audio/speech'


def _check_sidecar_health(*, timeout: float = 5.0) -> bool:
    global _availability_error, _sidecar_ok
    try:
        response = httpx.get(_health_url(), timeout=timeout)
        if response.status_code == 200:
            _sidecar_ok = True
            _availability_error = None
            return True
        _availability_error = f'svara health returned HTTP {response.status_code}'
        _sidecar_ok = False
        return False
    except Exception as exc:
        _availability_error = str(exc)
        _sidecar_ok = False
        return False


def svara_available() -> bool:
    if _sidecar_ok:
        return True
    return _check_sidecar_health(timeout=2.0)


def svara_ready() -> bool:
    return _ready


def svara_error() -> str | None:
    if _warmup_error:
        return _warmup_error
    if not svara_available():
        return _availability_error or f'svara sidecar unreachable at {SVARA_TTS_URL}'
    return None


class SvaraTtsManager:
    """Client for Kenpath svara OpenAI-compatible TTS API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_speaker = resolve_svara_speaker('hi')
        self._active_reply_script = 'hi'
        logger.info('svara HTTP client configured url=%s model=%s', SVARA_TTS_URL, SVARA_MODEL)

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
        if not _check_sidecar_health(timeout=10.0):
            raise RuntimeError(_availability_error or 'svara sidecar unhealthy')

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
        payload = {
            'model': SVARA_MODEL,
            'input': prepped,
            'voice': speaker,
            'response_format': 'pcm',
            'stream': True,
        }
        timeout = httpx.Timeout(SVARA_TTS_TIMEOUT_SEC, connect=10.0)

        with self._lock:
            with httpx.Client(timeout=timeout) as client:
                with client.stream('POST', _speech_url(), json=payload) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        if chunk:
                            yield (
                                ensure_pcm_s16le_bytes(chunk) or b'',
                                SAMPLE_RATE,
                            )

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
        _warmup_error = _availability_error or f'svara sidecar unreachable at {SVARA_TTS_URL}'
        logger.warning('svara warmup skipped: %s', _warmup_error)
        return
    try:
        mgr = get_manager()
        mgr.warmup()
        _ready = True
        _warmup_error = None
        logger.info('svara-TTS sidecar warmup complete (%s)', SVARA_TTS_URL)
    except Exception as exc:
        _warmup_error = str(exc)
        _ready = False
        logger.exception('svara-TTS warmup failed')
        raise

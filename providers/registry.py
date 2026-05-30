"""Factory for streaming STT/TTS providers."""

from __future__ import annotations

import logging

from config import STT_PROVIDER, TTS_PROVIDER
from providers.base import StreamingSTT, StreamingTTS

logger = logging.getLogger(__name__)

_OSS_STT = frozenset({'whisper', 'whisper_chunk', 'whisper-live'})
_TTS_PROVIDERS = frozenset({'f5', 'xtts', 'auto'})


def _f5_ok() -> bool:
    try:
        from engines.f5_tts_engine import f5_available

        return f5_available()
    except Exception:
        return False


def _xtts_ok() -> bool:
    try:
        from engines.xtts_engine import xtts_available

        return xtts_available()
    except Exception:
        return False


def resolve_tts_provider(name: str | None = None) -> str:
    resolved = (name or TTS_PROVIDER).lower()
    if resolved == 'auto':
        return 'f5' if _f5_ok() else 'xtts' if _xtts_ok() else 'f5'
    if resolved not in _TTS_PROVIDERS:
        logger.warning('TTS_PROVIDER=%r ignored; using f5', resolved)
        resolved = 'f5'
    if resolved == 'f5' and not _f5_ok():
        logger.warning('f5-tts not installed — run: bash scripts/install-f5-tts.sh')
    if resolved == 'xtts' and not _xtts_ok():
        logger.warning('coqui-tts not installed — run: bash scripts/install-xtts.sh')
    return resolved


def create_stt(provider: str | None = None) -> StreamingSTT:
    name = (provider or STT_PROVIDER).lower()
    if name == 'auto':
        name = 'whisper_chunk'
    if name not in _OSS_STT:
        raise ValueError(
            f'Unknown STT_PROVIDER={name!r}. Use whisper_chunk (open-source).'
        )
    if name == 'whisper_chunk':
        from providers.stt_whisper_chunk import WhisperChunkSTT

        return WhisperChunkSTT()
    from stt_worker import SttWorker

    return SttWorker()


def create_tts(provider: str | None = None) -> StreamingTTS:
    name = resolve_tts_provider(provider)
    if name == 'xtts':
        if not _xtts_ok():
            raise RuntimeError(
                'coqui-tts not installed. Run: bash scripts/install-xtts.sh'
            )
        from providers.tts_xtts import XTTSStreamingTTS

        return XTTSStreamingTTS()
    if not _f5_ok():
        if _xtts_ok():
            from providers.tts_xtts import XTTSStreamingTTS

            logger.warning('F5 unavailable; falling back to XTTS')
            return XTTSStreamingTTS()
        raise RuntimeError(
            'f5-tts not installed. Run: bash scripts/install-f5-tts.sh'
        )
    from providers.tts_f5 import F5StreamingTTS

    return F5StreamingTTS()


def auto_stt_provider() -> str:
    return 'whisper_chunk' if STT_PROVIDER == 'auto' else STT_PROVIDER


def auto_tts_provider() -> str:
    return resolve_tts_provider(TTS_PROVIDER)

"""Background model warmup state (non-blocking server start)."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_models_ready = False
_warmup_error: str | None = None
_warmup_started = False


def models_ready() -> bool:
    with _lock:
        return _models_ready


def warmup_error() -> str | None:
    with _lock:
        return _warmup_error


def run_warmup_background() -> None:
    global _warmup_started
    with _lock:
        if _warmup_started:
            return
        _warmup_started = True

    def _worker() -> None:
        global _models_ready, _warmup_error
        try:
            from config import STT_PROVIDER

            if STT_PROVIDER in ('whisper', 'whisper_chunk', 'whisper-live', 'silero_whisper', 'auto'):
                from stt_worker import FasterWhisperInferenceManager

                logger.info('Background warmup: Whisper STT...')
                FasterWhisperInferenceManager.for_language(None)

            from engines.silero_vad import warmup_silero_vad

            logger.info('Background warmup: Silero VAD...')
            warmup_silero_vad()

            from config import TTS_HINGLISH_ENGINE

            if TTS_HINGLISH_ENGINE == 'melotts':
                try:
                    from engines.melo_tts_engine import warmup as melo_warmup

                    logger.info('Background warmup: MeloTTS...')
                    melo_warmup()
                except Exception:
                    logger.warning('MeloTTS warmup skipped', exc_info=True)

            from engines.f5_tts_engine import f5_available, warmup as f5_warmup
            from engines.interjections import warmup_interjections

            if not f5_available():
                raise RuntimeError(
                    'f5-tts not installed. Run: bash scripts/install-f5-tts.sh'
                )
            logger.info('Background warmup: F5-TTS + Vocos...')
            f5_warmup()
            logger.info('Background warmup: interjection fillers...')
            warmup_interjections()

            with _lock:
                _models_ready = True
            logger.info('Background model warmup complete')
        except Exception as exc:
            logger.exception('Background warmup failed')
            with _lock:
                _warmup_error = str(exc)

    threading.Thread(target=_worker, name='model-warmup', daemon=True).start()

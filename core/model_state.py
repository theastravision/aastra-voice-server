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


def svara_ready() -> bool:
    try:
        from engines.svara_tts_engine import svara_ready as _svara_ready

        return _svara_ready()
    except Exception:
        return False


def svara_warmup_error() -> str | None:
    try:
        from engines.svara_tts_engine import svara_error

        return svara_error()
    except Exception as exc:
        return str(exc)


def run_warmup_background() -> None:
    global _warmup_started
    with _lock:
        if _warmup_started:
            return
        _warmup_started = True

    def _worker() -> None:
        global _models_ready, _warmup_error
        try:
            from config import STT_PROVIDER, TTS_INDIC_ENGINE

            if STT_PROVIDER in ('whisper', 'whisper_chunk', 'whisper-live', 'silero_whisper', 'auto'):
                from stt_worker import FasterWhisperInferenceManager

                logger.info('Background warmup: Whisper STT...')
                FasterWhisperInferenceManager.for_language(None)

            from engines.silero_vad import warmup_silero_vad

            logger.info('Background warmup: Silero VAD...')
            warmup_silero_vad()

            from engines.f5_tts_engine import f5_available, warmup as f5_warmup
            from engines.interjections import warmup_interjections

            if not f5_available():
                raise RuntimeError(
                    'f5-tts not installed. Run: bash scripts/install-f5-tts.sh'
                )
            logger.info('Background warmup: F5-TTS + Vocos (English)...')
            f5_warmup()

            if TTS_INDIC_ENGINE == 'svara':
                try:
                    from engines.svara_tts_engine import svara_available, warmup as svara_warmup

                    if svara_available():
                        logger.info('Background warmup: svara-TTS (Indic)...')
                        svara_warmup()
                    else:
                        logger.warning(
                            'TTS_INDIC_ENGINE=svara but svara not installed; '
                            'Indic sessions will fall back to F5. '
                            'Run: bash scripts/install-svara-tts.sh'
                        )
                except Exception:
                    logger.warning('svara-TTS warmup skipped', exc_info=True)

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

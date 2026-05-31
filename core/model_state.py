"""Background model warmup state (non-blocking server start)."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_models_ready = False
_warmup_error: str | None = None
_warmup_started = False
_svara_retry_started = False


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


def _try_svara_warmup() -> bool:
    from engines.svara_tts_engine import svara_available, warmup as svara_warmup

    if not svara_available():
        return False
    logger.info('Background warmup: svara-TTS (Indic)...')
    svara_warmup()
    return True


def _retry_svara_warmup_background() -> None:
    """Poll svara sidecar — vLLM can take several minutes after voice server starts."""
    global _svara_retry_started
    with _lock:
        if _svara_retry_started:
            return
        _svara_retry_started = True

    def _worker() -> None:
        from config import SVARA_TTS_URL, SVARA_WARMUP_POLL_SEC, SVARA_WARMUP_WAIT_SEC

        logger.info(
            'svara sidecar not ready yet — retrying up to %ss (%s)',
            SVARA_WARMUP_WAIT_SEC,
            SVARA_TTS_URL,
        )
        deadline = time.monotonic() + SVARA_WARMUP_WAIT_SEC
        while time.monotonic() < deadline:
            try:
                if _try_svara_warmup():
                    logger.info('svara-TTS sidecar ready after delayed warmup')
                    return
            except Exception as exc:
                logger.warning('svara retry warmup: %s', exc)
            time.sleep(max(1, SVARA_WARMUP_POLL_SEC))
        logger.warning(
            'svara sidecar still unreachable after %ss — Indic TTS will use F5 fallback',
            SVARA_WARMUP_WAIT_SEC,
        )

    threading.Thread(target=_worker, name='svara-warmup-retry', daemon=True).start()


def run_warmup_background() -> None:
    global _warmup_started
    with _lock:
        if _warmup_started:
            return
        _warmup_started = True

    def _worker() -> None:
        global _models_ready, _warmup_error
        errors: list[str] = []
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

            f5_ok = False
            if not f5_available():
                errors.append('f5-tts not installed (bash scripts/install-f5-tts.sh)')
            else:
                try:
                    logger.info('Background warmup: F5-TTS + Vocos (English)...')
                    f5_warmup()
                    f5_ok = True
                except Exception as exc:
                    logger.exception('F5-TTS warmup failed')
                    errors.append(f'F5: {exc}')

            svara_ok = False
            if TTS_INDIC_ENGINE == 'svara':
                try:
                    if _try_svara_warmup():
                        svara_ok = True
                    else:
                        logger.warning(
                            'svara sidecar not up yet (vLLM may still be loading in .venv-svara)'
                        )
                        if not f5_ok:
                            errors.append(
                                'svara sidecar unreachable '
                                '(bash scripts/install-svara-tts.sh && '
                                'bash scripts/run-svara-sidecar.sh --background)'
                            )
                        _retry_svara_warmup_background()
                except Exception as exc:
                    logger.exception('svara-TTS warmup failed')
                    if not f5_ok:
                        errors.append(f'svara: {exc}')
                    else:
                        _retry_svara_warmup_background()

            logger.info('Background warmup: interjection fillers...')
            warmup_interjections()

            if not f5_ok and not svara_ok:
                raise RuntimeError('; '.join(errors) if errors else 'No TTS engine warmed up')

            with _lock:
                _models_ready = True
                _warmup_error = '; '.join(errors) if errors else None
            logger.info(
                'Background model warmup complete (f5=%s svara=%s)',
                f5_ok,
                svara_ok,
            )
        except Exception as exc:
            logger.exception('Background warmup failed')
            with _lock:
                _warmup_error = str(exc)

    threading.Thread(target=_worker, name='model-warmup', daemon=True).start()

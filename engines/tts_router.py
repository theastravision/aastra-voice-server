"""Resolve TTS backend for English vs Hindi/Hinglish sessions."""

from __future__ import annotations

import logging

from config import TTS_HINGLISH_ENGINE

logger = logging.getLogger(__name__)

HinglishEngine = str  # f5_devanagari | f5 | xtts | melotts


def _xtts_ok() -> bool:
    try:
        from engines.xtts_engine import xtts_available

        return xtts_available()
    except Exception:
        return False


def _melotts_ok() -> bool:
    try:
        from engines.melo_tts_engine import melotts_available

        return melotts_available()
    except Exception:
        return False


def _fallback_hinglish_engine() -> HinglishEngine:
    logger.warning(
        'Requested Hinglish engine unavailable; falling back to f5_devanagari '
        '(install MeloTTS or set TTS_HINGLISH_ENGINE=f5_devanagari)'
    )
    return 'f5_devanagari'


def resolve_hinglish_engine() -> HinglishEngine:
    engine = TTS_HINGLISH_ENGINE.lower()
    if engine == 'xtts':
        if _xtts_ok():
            return 'xtts'
        logger.warning('TTS_HINGLISH_ENGINE=xtts but coqui-tts unavailable')
        if _melotts_ok():
            return 'melotts'
        return _fallback_hinglish_engine()
    if engine == 'melotts':
        if _melotts_ok():
            return 'melotts'
        return _fallback_hinglish_engine()
    if engine in ('f5', 'f5_devanagari'):
        return engine
    logger.warning('Unknown TTS_HINGLISH_ENGINE=%r; using f5_devanagari', engine)
    return 'f5_devanagari'


def resolve_tts_backend(reply_script: str | None) -> str:
    """Return synthesis backend id: f5 | xtts | melotts."""
    script = (reply_script or 'en').lower()
    if script in ('hi', 'hinglish'):
        hinglish = resolve_hinglish_engine()
        if hinglish == 'xtts':
            return 'xtts'
        if hinglish == 'melotts':
            return 'melotts'
    return 'f5'

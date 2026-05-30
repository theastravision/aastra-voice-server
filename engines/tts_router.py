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


def resolve_hinglish_engine() -> HinglishEngine:
    engine = TTS_HINGLISH_ENGINE.lower()
    if engine == 'xtts':
        if _xtts_ok():
            return 'xtts'
        logger.warning('TTS_HINGLISH_ENGINE=xtts but coqui-tts unavailable; using melotts')
        return 'melotts'
    if engine in ('f5', 'f5_devanagari', 'melotts'):
        return engine
    logger.warning('Unknown TTS_HINGLISH_ENGINE=%r; using melotts', engine)
    return 'melotts'


def resolve_tts_backend(reply_script: str | None) -> str:
    """Return 'f5' or 'xtts' for synthesis routing."""
    script = (reply_script or 'en').lower()
    if script in ('hi', 'hinglish'):
        hinglish = resolve_hinglish_engine()
        if hinglish == 'xtts':
            return 'xtts'
        if hinglish == 'melotts':
            return 'melotts'
    return 'f5'

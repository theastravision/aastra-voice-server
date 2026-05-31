"""Resolve TTS backend for English vs Indic language sessions."""

from __future__ import annotations

import logging

from config import TTS_INDIC_ENGINE, is_indic_reply_script

logger = logging.getLogger(__name__)


def resolve_tts_backend(reply_script: str | None) -> str:
    """Return synthesis backend id: f5 (English) | svara (Indic) | f5 fallback."""
    script = (reply_script or 'en').lower()
    if script == 'en':
        return 'f5'
    if is_indic_reply_script(script):
        if TTS_INDIC_ENGINE == 'svara':
            try:
                from engines.svara_tts_engine import svara_available

                if svara_available():
                    return 'svara'
            except Exception:
                logger.debug('svara availability check failed', exc_info=True)
        logger.warning('svara unavailable; falling back to F5 for reply_script=%s', script)
        return 'f5'
    return 'f5'

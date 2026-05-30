"""Shared interview greeting copy (delegates to interview_opening when enabled)."""

from __future__ import annotations

from engines.demo_bot import _greeting_text
from engines.interview_opening import opening_script
from engines.lang_detect import ReplyScript, SessionLanguage


def interview_greeting_text(
    name: str, session_lang: SessionLanguage | None
) -> tuple[str, ReplyScript]:
    """Return (spoken greeting, TTS route script)."""
    from engines.interview_opening import interview_opening_enabled

    if interview_opening_enabled():
        return opening_script(session_lang)
    return _greeting_text(name, session_lang)

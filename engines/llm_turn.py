"""Shared LLM extra-system assembly and script compliance for voice turns."""

from __future__ import annotations

import logging

from engines.lang_detect import SessionLanguage
from engines.llm_script_contract import (
    effective_session_lang,
    llm_language_hint_strict,
    script_retry_message,
    should_strict_script_gate,
    system_script_rules,
    validate_assistant_script,
)
from llm_worker import complete_chat_message, phrases_from_text

logger = logging.getLogger(__name__)


def build_extra_system(
    session_lang: SessionLanguage | None,
    reply_script: str,
    *,
    intro_follow_up: str | None = None,
) -> str:
    effective = effective_session_lang(session_lang, reply_script)
    if should_strict_script_gate() and effective in ('en', 'hi', 'hinglish'):
        hint = llm_language_hint_strict(effective)
        rules = system_script_rules(effective)
    else:
        from engines.lang_detect import llm_language_hint

        hint = llm_language_hint(reply_script)  # type: ignore[arg-type]
        rules = ''
    parts = [p for p in (rules, hint, intro_follow_up) if p]
    return '\n'.join(parts)


async def finalize_assistant_for_tts(
    messages: list[dict[str, str]],
    assistant_text: str,
    session_lang: SessionLanguage | None,
    reply_script: str,
) -> tuple[str, list[str]]:
    """Validate script compliance; optional one-shot LLM retry; return TTS phrases."""
    text = (assistant_text or '').strip()
    effective = effective_session_lang(session_lang, reply_script)

    if should_strict_script_gate() and effective in ('hi', 'hinglish') and text:
        if not validate_assistant_script(text, effective):
            logger.warning(
                'Assistant script non-compliant session=%s; retrying once',
                effective,
            )
            retry_messages = [
                *messages,
                {'role': 'assistant', 'content': text},
                {'role': 'user', 'content': script_retry_message(effective)},
            ]
            text = await complete_chat_message(retry_messages)
            if not validate_assistant_script(text, effective):
                logger.warning(
                    'Assistant script still non-compliant after retry; TTS pipeline fallback'
                )

    return text, phrases_from_text(text)

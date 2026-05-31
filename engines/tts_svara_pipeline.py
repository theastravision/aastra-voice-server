"""svara-TTS text preparation — native Indic script, punctuation prosody, no phonetic hacks."""

from __future__ import annotations

import re

from config import SVARA_EMOTION_TAG, TTS_DEVANAGARI_SOURCE, TTS_OUTPUT_SCRIPT
from engines.hinglish_normalize import normalize_hinglish
from engines.llm_script_contract import validate_assistant_script
from engines.tts_pacing import add_speech_pauses
from engines.tts_text_pipeline import (
    ReplyScript,
    normalize_mixed_script,
    to_devanagari_mixed,
)

_DEVANAGARI = re.compile(r'[\u0900-\u097F]')
_CURRENCY = re.compile(r'₹\s*([\d,]+(?:\.\d+)?)')
_DIGIT_RUN = re.compile(r'\b(\d{5,})\b')


def _normalize_numbers_for_svara(text: str) -> str:
    """Expand large numerals — svara handles words better than long digit runs."""

    def _expand_currency(m: re.Match[str]) -> str:
        raw = m.group(1).replace(',', '')
        return f'rupees {raw}'

    cleaned = _CURRENCY.sub(_expand_currency, text)
    return cleaned


def _append_emotion_tag(text: str) -> str:
    tag = (SVARA_EMOTION_TAG or '').strip()
    if not tag:
        return text
    if tag.startswith('<') and tag.endswith('>'):
        return f'{text.rstrip()} {tag}'
    return f'{text.rstrip()} <{tag}>'


def prepare_text_for_svara(
    text: str,
    *,
    reply_script: ReplyScript | str = 'hinglish',
    session_lang: str | None = None,
    llm_compliant: bool | None = None,
) -> str:
    """
    Prepare LLM output for svara-TTS: Devanagari/mixed script, pauses, optional emotion tag.
    Skips F5 phonetic hyphenation entirely.
    """
    script = (reply_script or 'hinglish').lower().strip()
    if script == 'en':
        return (text or '').strip()

    cleaned = normalize_hinglish(text)
    if not cleaned:
        return cleaned

    use_devanagari = script == 'hi' or (
        script == 'hinglish' and TTS_OUTPUT_SCRIPT == 'devanagari'
    )

    if use_devanagari and _DEVANAGARI.search(cleaned):
        result = normalize_mixed_script(cleaned)
    elif use_devanagari:
        use_llm_fast = TTS_DEVANAGARI_SOURCE == 'llm'
        compliant = llm_compliant
        if compliant is None and use_llm_fast and script in ('hi', 'hinglish'):
            from engines.llm_script_contract import effective_session_lang

            effective = effective_session_lang(session_lang, script)  # type: ignore[arg-type]
            compliant = validate_assistant_script(cleaned, effective)
        if use_llm_fast and compliant:
            result = normalize_mixed_script(cleaned)
        else:
            rs: ReplyScript = script if script in ('hi', 'hinglish') else 'hi'  # type: ignore[assignment]
            result = to_devanagari_mixed(cleaned, reply_script=rs)
    else:
        result = cleaned

    result = _normalize_numbers_for_svara(result)
    result = add_speech_pauses(result, reply_script='hinglish' if script == 'hinglish' else 'hi')
    return _append_emotion_tag(result)

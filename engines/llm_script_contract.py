"""Strict coupling between UI session language and GPT/TTS output script."""

from __future__ import annotations

import re
from typing import Literal

from config import TTS_HINGLISH_ROMAN, TTS_LLM_SCRIPT_STRICT, TTS_OUTPUT_SCRIPT
from engines.lang_detect import SessionLanguage, devanagari_ratio, is_mixed_script

OutputScript = Literal['en', 'devanagari']

_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_ROMAN_HINDI_MARKERS = frozenset(
    {
        'main',
        'mein',
        'mai',
        'aap',
        'aapko',
        'mujhe',
        'hai',
        'hain',
        'hoon',
        'ho',
        'batayiye',
        'boliye',
        'batao',
        'shuru',
        'karne',
        'karta',
        'karti',
        'pehle',
        'kripya',
        'naam',
        'maaf',
        'sun',
        'nahi',
        'nahin',
        'thoda',
        'apne',
        'baare',
        'batayiye',
        'namaste',
        'theek',
        'achha',
        'acha',
        'kya',
        'kyun',
        'kyu',
        'chaliye',
        'chalo',
        'lungi',
        'denge',
        'kijiye',
        'payi',
        'poora',
    }
)


def uses_devanagari_output() -> bool:
    return TTS_OUTPUT_SCRIPT == 'devanagari'


def uses_hinglish_roman() -> bool:
    """LLM outputs natural roman Hinglish (Latin), not forced Devanagari Hindi."""
    return TTS_HINGLISH_ROMAN


def output_script_for_session(session_lang: SessionLanguage | None) -> OutputScript:
    if session_lang == 'en':
        return 'en'
    if session_lang == 'hinglish' and uses_hinglish_roman():
        return 'en'
    if uses_devanagari_output() and session_lang in ('hi', 'hinglish'):
        return 'devanagari'
    if session_lang in ('hi', 'hinglish'):
        return 'devanagari'
    return 'en'


def _latin_tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _LATIN_WORD.finditer(text or '')]


def _roman_hindi_marker_count(text: str) -> int:
    return sum(1 for tok in _latin_tokens(text) if tok in _ROMAN_HINDI_MARKERS)


def validate_assistant_script(
    text: str,
    session_lang: SessionLanguage | None,
) -> bool:
    """True when assistant text matches the locked UI language script contract."""
    cleaned = (text or '').strip()
    if not cleaned:
        return True

    target = output_script_for_session(session_lang)

    if session_lang == 'hinglish' and uses_hinglish_roman():
        if devanagari_ratio(cleaned) >= 0.08 and _roman_hindi_marker_count(cleaned) == 0:
            return True
        if _roman_hindi_marker_count(cleaned) >= 1:
            return True
        if is_mixed_script(cleaned):
            return True
        return len(_latin_tokens(cleaned)) >= 2

    if target == 'en':
        if devanagari_ratio(cleaned) >= 0.05:
            return False
        return _roman_hindi_marker_count(cleaned) == 0

    if session_lang == 'hi':
        if devanagari_ratio(cleaned) < 0.25:
            return False
        return _roman_hindi_marker_count(cleaned) == 0

    # hinglish (Devanagari mode)
    if devanagari_ratio(cleaned) < 0.08:
        return False
    if _roman_hindi_marker_count(cleaned) > 0:
        return False
    return is_mixed_script(cleaned) or devanagari_ratio(cleaned) >= 0.15


def system_script_rules(session_lang: SessionLanguage | None) -> str:
    """Non-negotiable script rules appended to every GPT system/extra prompt."""
    target = output_script_for_session(session_lang)
    if target == 'en':
        return (
            'OUTPUT SCRIPT (mandatory): English only in Latin script. '
            'Do not use Hindi or Devanagari characters.'
        )
    if session_lang == 'hi':
        return (
            'OUTPUT SCRIPT (mandatory): Write Hindi in Devanagari only. '
            'Keep English technical terms in Latin (React, Python, API). '
            'Never romanize Hindi — do NOT write "main", "aap", "batayiye". '
            'Use warm, simple spoken Hindi (बताइए, समझ गई, बहुत अच्छा) — avoid heavy Sanskrit.'
        )
    return (
        'OUTPUT SCRIPT (mandatory): Hinglish session — write natural roman Hinglish in Latin script. '
        'Mix Hindi and English the way Indians speak: "Aap apne project ke baare mein batayiye." '
        'English tech terms stay English (React, FastAPI, engineer). '
        'VOICE PACE: Speak slowly and clearly when read aloud — use commas for natural pauses, '
        'short clauses, warm storyteller tone. Never rush between Hindi and English words.'
    )


def llm_language_hint_strict(session_lang: SessionLanguage | None) -> str:
    """Per-turn hint tightly coupled to frontend language selection."""
    if session_lang == 'en':
        return (
            'CRITICAL: Reply in English only using Latin script. '
            'No Devanagari. Maximum twelve spoken words per turn.'
        )
    if session_lang == 'hi':
        return (
            'CRITICAL: Reply in Hindi using Devanagari for all Hindi words '
            '(e.g. मैं आपका interview लूँगी). Latin only for English tech terms. '
            'Never use romanized Hindi. Warm, simple spoken tone. '
            'Maximum twelve spoken words per turn.'
        )
    if session_lang == 'hinglish':
        return (
            'CRITICAL: Reply in natural roman Hinglish (Latin script only). '
            'Example: "Phir Aashish ne decide kiya, ki woh engineer banega." '
            'Mix Hindi and English naturally; tech words in English. '
            'Speak slowly for voice: use commas where you pause, short warm clauses, '
            'never rush. Maximum twelve spoken words per turn.'
        )
    return llm_language_hint_strict('hinglish')


def script_retry_message(session_lang: SessionLanguage | None) -> str:
    return (
        f'{system_script_rules(session_lang)} '
        'Your previous reply used the wrong script. Rewrite the entire reply correctly. '
        'Output only the corrected spoken reply, nothing else.'
    )


def should_strict_script_gate() -> bool:
    return TTS_LLM_SCRIPT_STRICT and uses_devanagari_output()


def effective_session_lang(
    session_lang: SessionLanguage | None,
    reply_script: str,
) -> SessionLanguage | None:
    """Prefer locked UI language over detected reply script for script contract."""
    if session_lang in ('en', 'hi', 'hinglish'):
        return session_lang
    if reply_script in ('en', 'hi', 'hinglish'):
        return reply_script  # type: ignore[return-value]
    return None

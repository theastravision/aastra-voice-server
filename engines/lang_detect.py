"""Language / script detection for Hindi, English, and Hinglish."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from engines.stt_names import whisper_names_prompt

ReplyScript = Literal['en', 'hi', 'hinglish']
TtsRoute = Literal['en', 'hi', 'hinglish']
SessionLanguage = Literal['en', 'hi', 'hinglish', 'auto']

_DEVANAGARI = re.compile(r'[\u0900-\u097F]')
_LATIN = re.compile(r'[A-Za-z]')

_SCRIPT_SPLIT = re.compile(
    r'([\u0900-\u097F]+|[A-Za-z][A-Za-z0-9\'’\-]*)',
)


def devanagari_ratio(text: str) -> float:
    if not text:
        return 0.0
    dev = len(_DEVANAGARI.findall(text))
    return dev / max(len(text.replace(' ', '')), 1)


def latin_ratio(text: str) -> float:
    if not text:
        return 0.0
    lat = len(_LATIN.findall(text))
    return lat / max(len(text.replace(' ', '')), 1)


def is_mixed_script(text: str) -> bool:
    """True when text has both meaningful Devanagari and Latin."""
    return devanagari_ratio(text) >= 0.08 and latin_ratio(text) >= 0.08


def normalize_whisper_lang(code: str | None) -> str | None:
    if not code or code == 'auto':
        return None
    c = code.lower().split('-')[0]
    if c in ('en', 'hi', 'hinglish'):
        return c if c != 'hinglish' else None
    if c.startswith('hi'):
        return 'hi'
    return c


def resolve_session_language(hint: str | None) -> SessionLanguage | None:
    """Normalize UI/WS language hint. None = auto-detect mode."""
    if not hint:
        return None
    c = hint.lower().strip().split('-')[0]
    if c in ('auto', ''):
        return None
    if c == 'hinglish':
        return 'hinglish'
    if c in ('hi', 'hindi'):
        return 'hi'
    if c in ('en', 'english'):
        return 'en'
    return None


def resolve_whisper_language(explicit: str | None = None) -> str | None:
    """Language passed to faster-whisper; None = auto-detect (best for Hinglish)."""
    session = resolve_session_language(explicit)
    if session == 'hi':
        return 'hi'
    if session == 'en':
        return 'en'
    if session == 'hinglish':
        return None
    if explicit is not None and explicit.lower() not in ('auto', ''):
        return normalize_whisper_lang(explicit)
    if WHISPER_LANGUAGE == 'auto':
        return None
    return normalize_whisper_lang(WHISPER_LANGUAGE)


_WHISPER_INTERVIEW_EN_PROMPT = (
    'Technical software engineering interview in English. '
    'Terms: software development, programming, APIs, databases, system design. '
    + whisper_names_prompt(40)
)


def _generated_whisper_prompt() -> str | None:
    path = Path(HINGLISH_VOCAB_DIR) / 'whisper_hinglish_prompt.txt'
    if not path.is_file():
        return None
    text = path.read_text(encoding='utf-8').strip()
    return text or None


def whisper_initial_prompt(language: str | None) -> str | None:
    names = whisper_names_prompt(36)
    if language == 'hi':
        return f'यह हिंदी में तकनीकी साक्षात्कार है। {names}'
    if language == 'en':
        return _WHISPER_INTERVIEW_EN_PROMPT
    generated = _generated_whisper_prompt()
    base = WHISPER_INITIAL_PROMPT or generated or ''
    if WHISPER_LANGUAGE == 'auto' or not language:
        return f'{base} {names}'.strip() if base else names
    return f'{base} {names}'.strip() if base else names


def pick_reply_script_for_session(
    session_lang: SessionLanguage | None,
    detected_lang: str | None,
    user_text: str,
) -> ReplyScript:
    """Apply locked session language when user selects en/hi/hinglish."""
    if session_lang == 'en':
        return 'en'
    if session_lang == 'hi':
        return 'hi'
    if session_lang == 'hinglish':
        return 'hinglish'
    return pick_reply_script(detected_lang, user_text)


def pick_tts_route_for_session(
    session_lang: SessionLanguage | None,
    reply_script: ReplyScript,
) -> TtsRoute:
    if session_lang == 'en':
        return 'en'
    if session_lang == 'hi':
        return 'hi'
    if session_lang == 'hinglish':
        return 'hinglish'
    return pick_tts_route(reply_script)


def empty_utterance_message(session_lang: SessionLanguage | None) -> tuple[str, ReplyScript]:
    from engines.llm_script_contract import uses_devanagari_output

    devanagari = uses_devanagari_output()
    if session_lang == 'hi':
        if devanagari:
            return 'माफ़ कीजिए, मैं सुन नहीं पाई। कृपया दोबारा बोलिए।', 'hi'
        return 'Maaf kijiye, main sun nahi payi. Kripya dobara boliye.', 'hi'
    if session_lang == 'hinglish':
        if devanagari:
            return 'Sorry, मैं सुन नहीं पाई। कृपया दोबारा बोलिए।', 'hinglish'
        return 'Sorry, main sun nahi payi. Kripya dobara boliye.', 'hinglish'
    return 'Sorry, I did not catch that. Please say it again.', 'en'


def pick_reply_script(detected_lang: str | None, user_text: str) -> ReplyScript:
    if is_mixed_script(user_text):
        return 'hinglish'
    code = normalize_whisper_lang(detected_lang)
    if code == 'hi':
        return 'hi'
    if code == 'en':
        return 'en'
    if devanagari_ratio(user_text) >= 0.15:
        return 'hi'
    if latin_ratio(user_text) >= 0.2:
        return 'en'
    return 'hinglish'


def pick_tts_route(reply_script: ReplyScript) -> TtsRoute:
    if reply_script == 'hinglish':
        return 'hinglish'
    if reply_script == 'hi':
        return 'hi'
    return 'en'


def pick_tts_route_from_text(text: str, fallback: ReplyScript = 'en') -> TtsRoute:
    if is_mixed_script(text):
        return 'hinglish'
    if devanagari_ratio(text) >= 0.1:
        return 'hi'
    if fallback == 'hinglish':
        return 'hinglish'
    return 'en'


def split_text_by_script(text: str) -> list[tuple[str, Literal['en', 'hi']]]:
    """Split into alternating Latin (en) and Devanagari (hi) runs for Kokoro."""
    cleaned = (text or '').strip()
    if not cleaned:
        return []
    segments: list[tuple[str, Literal['en', 'hi']]] = []
    for part in _SCRIPT_SPLIT.findall(cleaned):
        p = part.strip()
        if not p:
            continue
        if _DEVANAGARI.search(p):
            segments.append((p, 'hi'))
        elif _LATIN.search(p):
            segments.append((p, 'en'))
    if not segments:
        route: Literal['en', 'hi'] = 'hi' if devanagari_ratio(cleaned) >= 0.15 else 'en'
        return [(cleaned, route)]
    merged: list[tuple[str, Literal['en', 'hi']]] = []
    for seg, lang in segments:
        if merged and merged[-1][1] == lang:
            merged[-1] = (merged[-1][0] + ' ' + seg, lang)
        else:
            merged.append((seg, lang))
    return merged


def llm_language_hint(reply_script: ReplyScript) -> str:
    from config import TTS_LLM_SCRIPT_STRICT
    from engines.llm_script_contract import llm_language_hint_strict, uses_devanagari_output

    if TTS_LLM_SCRIPT_STRICT and uses_devanagari_output():
        return llm_language_hint_strict(reply_script)
    devanagari_tts = TTS_OUTPUT_SCRIPT == 'devanagari'
    if devanagari_tts and reply_script == 'hi':
        return (
            'CRITICAL: Reply in Hindi using Devanagari script for Hindi words '
            '(e.g. मैं आपका interview लूँगी). Keep English technical terms in Latin. '
            'Never romanize Hindi. Maximum twelve spoken words per turn.'
        )
    if devanagari_tts and reply_script == 'hinglish':
        return (
            'CRITICAL: Hinglish session — Hindi words in Devanagari, English/tech in Latin. '
            'Do NOT write "Shuru karne se pehle" — write "शुरू करने से पहले". '
            'Maximum twelve spoken words per turn.'
        )
    return {
        'en': (
            'CRITICAL: Reply in English only using Latin script. '
            'Do not use Hindi or Devanagari. Maximum twelve spoken words per turn.'
        ),
        'hi': (
            'CRITICAL: Reply in Hindi using Latin/romanized script only '
            '(e.g. Main aapka interview lungi). No Devanagari characters. '
            'Maximum twelve spoken words per turn.'
        ),
        'hinglish': (
            'The user is speaking Hinglish (mixed Hindi and English). '
            'Reply in natural Hinglish using Latin script only — no Devanagari. '
            'Maximum twelve spoken words per turn.'
        ),
    }.get(reply_script, '')

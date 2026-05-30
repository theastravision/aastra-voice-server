"""STT post-processing: hallucination filters and listen-idle prompts."""

from __future__ import annotations

import re

from config import STREAM_STT_MIN_CHARS
from engines.lang_detect import SessionLanguage

# Whisper often hallucinates these on silence / background noise (HAR-confirmed).
_PHANTOM_EXACT = frozenset(
    {
        'thank you',
        'thank you.',
        'thanks',
        'thanks.',
        'thank you so much',
        'thank you so much.',
        'thanks for watching',
        'thanks for watching.',
        'you',
        'bye',
        'bye.',
        'okay',
        'okay.',
        'ok',
        'ok.',
        'hmm',
        'hmm.',
        'um',
        'um.',
        'uh',
        'uh.',
        'the',
        'the.',
        'subtitle by',
        'subtitles by',
        'llm.',
        'llm',
        'on.',
        'on',
        'and...',
        'and.',
    }
)

_PHANTOM_SUBSTR = (
    'thank you for watching',
    'subscribe',
    'like and subscribe',
    'www.',
    '.com',
    '.au',
    'http://',
    'https://',
)

_REPEAT_INTENT = re.compile(
    r'\b('
    r'yes|yeah|yep|please repeat|repeat (the )?question|say (it )?again|'
    r'can you repeat|repeat please|once more|dobara|phir se|haan|haan ji'
    r')\b',
    re.IGNORECASE,
)


def _is_repeated_word_hallucination(text: str) -> bool:
    """True when the same token repeats 3+ times (e.g. 'terms. terms. terms.')."""
    words = re.findall(r'[\w\u0900-\u097F]+', normalize_stt_text(text))
    if len(words) < 3:
        return False
    if len(set(words)) == 1:
        return True
    for i in range(len(words) - 2):
        if words[i] == words[i + 1] == words[i + 2]:
            return True
    return False


def normalize_stt_text(text: str) -> str:
    return ' '.join((text or '').strip().lower().split())


def is_phantom_stt_text(text: str) -> bool:
    """True if transcript is likely noise/silence hallucination, not real speech."""
    norm = normalize_stt_text(text)
    if not norm:
        return True
    if norm in _PHANTOM_EXACT:
        return True
    if any(p in norm for p in _PHANTOM_SUBSTR):
        return True
    if _is_repeated_word_hallucination(text):
        return True
    return False


def is_substantive_utterance(text: str, *, min_chars: int = 8) -> bool:
    cleaned = (text or '').strip()
    if len(cleaned) < min_chars:
        return False
    if is_phantom_stt_text(cleaned):
        return False
    return bool(re.search(r'[\w\u0900-\u097F]', cleaned, re.UNICODE))


def pick_best_stt_text(*candidates: str | None, min_chars: int | None = None) -> str:
    """Return the longest substantive transcript among candidates."""
    threshold = min_chars if min_chars is not None else STREAM_STT_MIN_CHARS
    best = ''
    for candidate in candidates:
        text = (candidate or '').strip()
        if not is_substantive_utterance(text, min_chars=threshold):
            continue
        if len(text) > len(best):
            best = text
    return best


def is_repeat_intent(text: str) -> bool:
    return bool(_REPEAT_INTENT.search(text or ''))


def listen_idle_message(session_lang: SessionLanguage | None) -> tuple[str, str]:
    """After ~8s silence: ask if candidate wants the question repeated."""
    if session_lang == 'hi':
        return (
            'Kya aap jawab dena chahenge? Kya main sawaal dohraoon?',
            'hi',
        )
    if session_lang == 'hinglish':
        return (
            'Kya aap jawab dena chahenge? Kya main question repeat karoon?',
            'hinglish',
        )
    return (
        'Can you please reply? Would you like me to repeat the question for you?',
        'en',
    )


def repeat_last_question_message(session_lang: SessionLanguage | None) -> tuple[str, str]:
    if session_lang == 'hi':
        return 'Theek hai, main aakhri sawaal dohraati hoon.', 'hi'
    if session_lang == 'hinglish':
        return 'Theek hai, main last question repeat karti hoon.', 'hinglish'
    return 'Sure, I will repeat the last question.', 'en'

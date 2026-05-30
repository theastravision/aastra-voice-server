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
    r'please repeat|repeat (the )?question|say (it )?again|'
    r'can you repeat|repeat please|once more|dobara|phir se|'
    r'question repeat|sawaal dohra'
    r')\b',
    re.IGNORECASE,
)

_SHORT_AFFIRM = re.compile(
    r'^(yes|yeah|yep|haan|haan ji)[\s,.!?]*$',
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


def dedupe_repeated_sentences(text: str) -> str:
    """Collapse duplicate sentences/clauses from Whisper echo or double-flush."""
    cleaned = (text or '').strip()
    if not cleaned:
        return ''
    cleaned = _collapse_duplicate_halves(cleaned)
    parts = re.split(r'(?<=[.!?])\s+', cleaned)
    if len(parts) <= 1:
        return cleaned
    out: list[str] = []
    prev_norm = ''
    for part in parts:
        p = part.strip()
        if not p:
            continue
        norm = normalize_stt_text(p)
        if norm and norm != prev_norm:
            out.append(p if p[-1] in '.!?' else f'{p}.')
            prev_norm = norm
    joined = ' '.join(out).strip()
    if not joined:
        return cleaned
    return joined.rstrip('.') + '.' if joined[-1] not in '.!?' else joined


def _collapse_duplicate_halves(text: str) -> str:
    """If transcript is two near-identical halves, keep one."""
    norm_full = normalize_stt_text(text)
    words = text.split()
    if len(words) < 6:
        return text
    mid = len(words) // 2
    first = normalize_stt_text(' '.join(words[:mid]))
    second = normalize_stt_text(' '.join(words[mid:]))
    if first and first == second:
        return ' '.join(words[:mid])
    if len(first) > 12 and (first in second or second in first):
        return ' '.join(words[:mid])
    return text


def postprocess_stt_transcript(text: str) -> str:
    """Dedupe + name correction pipeline."""
    from engines.stt_names import correct_names_in_transcript

    cleaned = dedupe_repeated_sentences((text or '').strip())
    return correct_names_in_transcript(cleaned)


def is_repeat_intent(text: str) -> bool:
    """True only for short repeat requests — not when echo pollutes a real answer."""
    cleaned = (text or '').strip()
    if not cleaned:
        return False
    if re.search(
        r'\b(my name is|mera naam|i am|i\'m|main hoon|this is)\b',
        cleaned,
        re.IGNORECASE,
    ):
        return False
    if _REPEAT_INTENT.search(cleaned):
        return len(cleaned) <= 80
    return len(cleaned) <= 24 and bool(_SHORT_AFFIRM.match(cleaned))


def listen_idle_message(session_lang: SessionLanguage | None) -> tuple[str, str]:
    """After silence while waiting for an answer: offer repeat or more thinking time."""
    from engines.llm_script_contract import uses_devanagari_output

    devanagari = uses_devanagari_output()
    if session_lang == 'hi':
        if devanagari:
            return (
                'क्या आप अभी भी जवाब सोच रहे हैं, या मैं सवाल दोहराऊँ?',
                'hi',
            )
        return (
            'Kya aap abhi bhi jawab soch rahe hain, ya main sawaal dohraoon?',
            'hi',
        )
    if session_lang == 'hinglish':
        if devanagari:
            return (
                'क्या आप अभी भी answer सोच रहे हैं, या मैं question repeat करूँ?',
                'hinglish',
            )
        return (
            'Kya aap abhi bhi answer soch rahe hain, ya main question repeat karoon?',
            'hinglish',
        )
    return (
        'Are you still thinking the answer, or would you like me to repeat this question?',
        'en',
    )


def repeat_last_question_message(session_lang: SessionLanguage | None) -> tuple[str, str]:
    from engines.llm_script_contract import uses_devanagari_output

    devanagari = uses_devanagari_output()
    if session_lang == 'hi':
        if devanagari:
            return 'ठीक है, मैं आखिरी सवाल दोहराती हूँ।', 'hi'
        return 'Theek hai, main aakhri sawaal dohraati hoon.', 'hi'
    if session_lang == 'hinglish':
        if devanagari:
            return 'ठीक है, मैं last question repeat करती हूँ।', 'hinglish'
        return 'Theek hai, main last question repeat karti hoon.', 'hinglish'
    return 'Sure, I will repeat the last question.', 'en'

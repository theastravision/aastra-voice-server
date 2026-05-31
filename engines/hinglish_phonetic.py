"""Optional roman phonetic transforms for Hinglish TTS (disabled by default).

Hyphen and space syllable breaks both sound unnatural on F5/Swara, so the pipeline
passes LLM text through unchanged unless TTS_HINGLISH_PHONETIC_HYPHEN=true.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from config import (
    HINGLISH_VOCAB_DIR,
    STT_HINGLISH_PHONETIC_DENORM,
    TTS_HINGLISH_PHONETIC_HYPHEN,
)

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_DEVANAGARI = re.compile(r'[\u0900-\u097F]')
_VOCAB_MTIME: float = 0.0


def _vocab_path() -> Path:
    return Path(HINGLISH_VOCAB_DIR) / 'hinglish_phonetic_hyphens.json'


@lru_cache(maxsize=1)
def _load_glossary_cached() -> dict[str, str]:
    path = _vocab_path()
    merged: dict[str, str] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            for section in ('loanwords', 'hindi_roman'):
                for key, value in (data.get(section) or {}).items():
                    merged[str(key).lower()] = str(value)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning('Failed to load phonetic map: %s', exc)
    return merged


def _load_glossary() -> dict[str, str]:
    global _VOCAB_MTIME
    path = _vocab_path()
    if path.is_file():
        mtime = path.stat().st_mtime
        if mtime != _VOCAB_MTIME:
            _load_glossary_cached.cache_clear()
            _VOCAB_MTIME = mtime
    return _load_glossary_cached()


def _preserve_case(original: str, replacement: str) -> str:
    if not original or not replacement:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        parts = replacement.split('-')
        head = parts[0].capitalize() if parts[0] else parts[0]
        return '-'.join([head, *(p.lower() for p in parts[1:])])
    return replacement


def _replace_word(word: str, mapping: dict[str, str]) -> str:
    if '-' in word:
        return word
    mapped = mapping.get(word.lower())
    if not mapped:
        return word
    return _preserve_case(word, mapped)


def apply_phonetic_hyphens(text: str, *, reply_script: str = 'hinglish') -> str:
    """Pass text through unchanged unless explicit static glossary override is enabled."""
    cleaned = (text or '').strip()
    if not cleaned:
        return cleaned
    if not TTS_HINGLISH_PHONETIC_HYPHEN or reply_script not in ('hi', 'hinglish'):
        return cleaned

    glossary = _load_glossary()
    if not glossary:
        return cleaned

    def _sub(match: re.Match[str]) -> str:
        return _replace_word(match.group(0), glossary)

    return _WORD.sub(_sub, cleaned)


@lru_cache(maxsize=1)
def _reverse_glossary_cached() -> dict[str, str]:
    reverse: dict[str, str] = {}
    for key, value in _load_glossary_cached().items():
        reverse[value.lower()] = key
        reverse[value.lower().replace('-', '').replace(' ', '')] = key
    return reverse


def denormalize_phonetic_word(word: str) -> str:
    if not word or ('-' not in word and ' ' not in word):
        return word
    lower = word.lower()
    reverse = _reverse_glossary_cached()
    canonical = reverse.get(lower) or reverse.get(lower.replace('-', '').replace(' ', ''))
    if canonical:
        return _preserve_case(word, canonical)
    return word.replace('-', '').replace(' ', '')


def denormalize_phonetic_text(text: str, *, reply_script: str | None = None) -> str:
    if not STT_HINGLISH_PHONETIC_DENORM:
        return (text or '').strip()
    if reply_script == 'en':
        return (text or '').strip()

    cleaned = (text or '').strip()
    if not cleaned or _DEVANAGARI.search(cleaned):
        return cleaned

    glossary = _load_glossary_cached()
    result = cleaned
    for canonical, phonetic in sorted(glossary.items(), key=lambda item: len(item[1]), reverse=True):
        result = re.sub(re.escape(phonetic), canonical, result, flags=re.IGNORECASE)

    def _replace(match: re.Match[str]) -> str:
        return denormalize_phonetic_word(match.group(0))

    return _WORD.sub(_replace, result)


class HinglishPhoneticEngine:
    """Legacy alias — static glossary only when phonetic flag is on."""

    def transform_word(self, word: str) -> str:
        return _replace_word(word, _load_glossary())

    def process_sentence(self, sentence: str) -> str:
        return apply_phonetic_hyphens(sentence, reply_script='hinglish')


def get_phonetic_engine() -> HinglishPhoneticEngine:
    return HinglishPhoneticEngine()

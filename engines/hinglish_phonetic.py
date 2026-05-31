"""Dynamic roman phonetic spacing for Hinglish/Hindi TTS and STT denormalization."""

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
    TTS_HINGLISH_PHONETIC_MIN_LEN,
    TTS_HINGLISH_PHONETIC_SEPARATOR,
)

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_DEVANAGARI = re.compile(r'[\u0900-\u097F]')
_VOCAB_MTIME: float = 0.0
_NAMES_MTIME: float = 0.0

# VCV syllable split for unseen roman tokens
_SYLLABLE_REGEX = re.compile(
    r'([^aeiouy]*[aeiouy]+(?:[^aeiouy](?![aeiouy]))*)',
    re.IGNORECASE,
)

# Mutations must not introduce hyphens — F5/Swara reads "-" as a harsh foreign cue
_PHONETIC_MUTATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r'ci', re.IGNORECASE), 'si'),
    (re.compile(r'ch', re.IGNORECASE), 'k'),
    (re.compile(r'gy$', re.IGNORECASE), 'jee'),
    (re.compile(r'^de(?=[b-df-hj-np-tv-z])', re.IGNORECASE), 'dee'),
    (re.compile(r'tion', re.IGNORECASE), 'shun'),
)

_BUILTIN_GLOSSARY: dict[str, str] = {
    'decide': 'dee sa eed',
    'decided': 'dee sa eed ed',
    'engineer': 'in jin eer',
    'engineering': 'in jin eer ing',
    'technology': 'tek no lo jee',
    'technologies': 'tek no lo jeez',
    'software': 'soft ware',
    'developer': 'de vel o per',
    'technical': 'tek ni cal',
    'experience': 'ex pe ri ence',
    'interview': 'in ter view',
    'zindagi': 'zin da gi',
    'aasaan': 'aa saan',
    'asaan': 'aa saan',
}


def _syllable_sep() -> str:
    mode = TTS_HINGLISH_PHONETIC_SEPARATOR
    if mode == 'none':
        return ''
    if mode == 'hyphen':
        return '-'
    return ' '


def _normalize_phonetic_form(value: str) -> str:
    """Map JSON/hyphen legacy forms to the active TTS separator."""
    sep = _syllable_sep()
    cleaned = re.sub(r'[\s\-]+', ' ', (value or '').strip())
    if sep == ' ':
        return cleaned
    if sep == '':
        return cleaned.replace(' ', '')
    return cleaned.replace(' ', sep)


def _vocab_path() -> Path:
    return Path(HINGLISH_VOCAB_DIR) / 'hinglish_phonetic_hyphens.json'


def _names_path() -> Path:
    return Path(HINGLISH_VOCAB_DIR) / 'interview_names.txt'


@lru_cache(maxsize=1)
def _load_json_maps_cached() -> tuple[dict[str, str], dict[str, str]]:
    path = _vocab_path()
    if not path.is_file():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning('Failed to load phonetic map: %s', exc)
        return {}, {}
    loanwords = {
        str(k).lower(): _normalize_phonetic_form(str(v))
        for k, v in (data.get('loanwords') or {}).items()
    }
    hindi = {
        str(k).lower(): _normalize_phonetic_form(str(v))
        for k, v in (data.get('hindi_roman') or {}).items()
    }
    return loanwords, hindi


def _load_json_maps() -> tuple[dict[str, str], dict[str, str]]:
    global _VOCAB_MTIME
    path = _vocab_path()
    if path.is_file():
        mtime = path.stat().st_mtime
        if mtime != _VOCAB_MTIME:
            _load_json_maps_cached.cache_clear()
            _load_glossary_cached.cache_clear()
            _reverse_glossary_cached.cache_clear()
            _VOCAB_MTIME = mtime
    return _load_json_maps_cached()


@lru_cache(maxsize=1)
def _load_glossary_cached() -> dict[str, str]:
    loanwords, hindi = _load_json_maps_cached()
    merged = {k: _normalize_phonetic_form(v) for k, v in _BUILTIN_GLOSSARY.items()}
    merged.update(hindi)
    merged.update(loanwords)
    return merged


@lru_cache(maxsize=1)
def _load_skip_particles_cached() -> frozenset[str]:
    from engines.hinglish_vocab import hinglish_particles

    return hinglish_particles()


@lru_cache(maxsize=1)
def _load_skip_names_cached() -> frozenset[str]:
    path = _names_path()
    if not path.is_file():
        return frozenset()
    try:
        return frozenset(line.strip().lower() for line in path.read_text(encoding='utf-8').splitlines() if line.strip())
    except OSError:
        return frozenset()


def _split_phonetic_parts(value: str) -> list[str]:
    sep = _syllable_sep()
    if sep:
        return [p for p in re.split(re.escape(sep), value) if p]
    # none: split on camel-ish syllable boundaries for casing only
    return [value]


def _preserve_case(original: str, replacement: str) -> str:
    if not original or not replacement:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        parts = _split_phonetic_parts(replacement)
        if not parts:
            return replacement
        head = parts[0].capitalize() if parts[0] else parts[0]
        sep = _syllable_sep()
        tail = sep.join(p.lower() for p in parts[1:]) if sep else ''.join(p.lower() for p in parts[1:])
        return f'{head}{sep}{tail}' if tail else head
    return replacement


def _join_syllables(parts: list[str]) -> str:
    sep = _syllable_sep()
    if sep:
        return sep.join(parts)
    return ''.join(parts)


def _mutate_syllable(syllable: str) -> str:
    mutated = syllable
    for pattern, substitution in _PHONETIC_MUTATIONS:
        mutated = pattern.sub(substitution, mutated)
    return mutated


def _sanitize_tts_output(text: str) -> str:
    """Strip hyphen artifacts — F5 reads them as unnatural clipped phonemes."""
    if _syllable_sep() == '-':
        return text
    cleaned = text.replace('-', ' ')
    return re.sub(r'\s+', ' ', cleaned).strip()


@lru_cache(maxsize=8192)
def _transform_word_cached(lowered: str) -> str:
    glossary = _load_glossary_cached()
    if lowered in glossary:
        return glossary[lowered]

    syllables = [m.group(0) for m in _SYLLABLE_REGEX.finditer(lowered) if m.group(0)]
    if len(syllables) <= 1:
        return lowered

    processed = [_mutate_syllable(syl) for syl in syllables]
    return _join_syllables(processed) or lowered


class HinglishPhoneticEngine:
    """Deterministic roman syllable spacing for Hinglish/Hindi TTS."""

    def should_skip(self, word: str) -> bool:
        if not word:
            return True
        if _DEVANAGARI.search(word):
            return True
        lower = word.lower()
        if len(lower) < TTS_HINGLISH_PHONETIC_MIN_LEN:
            return True
        if lower in _load_skip_particles_cached():
            return True
        if lower in _load_skip_names_cached():
            return True
        if word.isupper() and len(word) >= 2:
            return True
        return False

    def transform_word(self, word: str) -> str:
        if self.should_skip(word):
            return word
        if '-' in word:
            return _sanitize_tts_output(word)
        lowered = word.lower()
        transformed = _transform_word_cached(lowered)
        if transformed == lowered:
            return word
        return _preserve_case(word, transformed)

    def process_sentence(self, sentence: str) -> str:
        if not sentence:
            return ''

        def _replace(match: re.Match[str]) -> str:
            return self.transform_word(match.group(0))

        return _sanitize_tts_output(_WORD.sub(_replace, sentence))


_engine: HinglishPhoneticEngine | None = None


def get_phonetic_engine() -> HinglishPhoneticEngine:
    global _engine
    if _engine is None:
        _engine = HinglishPhoneticEngine()
    return _engine


def apply_phonetic_hyphens(text: str, *, reply_script: str = 'hinglish') -> str:
    """
    Space roman syllables for clearer F5/Swara articulation (no literal hyphens).
    Uses static glossary overrides plus dynamic syllabification for unseen words.
    """
    if not TTS_HINGLISH_PHONETIC_HYPHEN or reply_script not in ('hi', 'hinglish'):
        return (text or '').strip()

    cleaned = (text or '').strip()
    if not cleaned:
        return cleaned

    return get_phonetic_engine().process_sentence(cleaned)


@lru_cache(maxsize=1)
def _reverse_glossary_cached() -> dict[str, str]:
    glossary = _load_glossary_cached()
    reverse: dict[str, str] = {}
    for key, value in glossary.items():
        reverse[value.lower()] = key
        reverse[value.lower().replace(' ', '')] = key
        reverse[value.lower().replace(' ', '-')] = key
        reverse[value.lower().replace('-', ' ')] = key
    return reverse


@lru_cache(maxsize=4096)
def _denormalize_word_cached(word_lower: str) -> str:
    reverse = _reverse_glossary_cached()
    if word_lower in reverse:
        return reverse[word_lower]
    compact = word_lower.replace('-', '').replace(' ', '')
    if compact in reverse:
        return reverse[compact]
    if '-' in word_lower:
        return word_lower.replace('-', '')
    return word_lower


def denormalize_phonetic_word(word: str) -> str:
    """Map a spaced phonetic token back to canonical roman spelling."""
    if not word:
        return word
    lower = word.lower()
    if '-' not in lower and ' ' not in lower:
        return word
    canonical = _denormalize_word_cached(lower)
    if canonical == lower.replace('-', '').replace(' ', ''):
        return word.replace('-', '').replace(' ', '')
    if canonical != lower:
        return _preserve_case(word, canonical)
    return word.replace('-', '').replace(' ', '')


def denormalize_phonetic_text(text: str, *, reply_script: str | None = None) -> str:
    """
    Reverse TTS phonetic spacing in STT transcripts for hi/hinglish sessions.
    Restores glossary loanwords and joins dynamic syllable spaces.
    """
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
        pattern = re.compile(re.escape(phonetic), re.IGNORECASE)
        result = pattern.sub(canonical, result)
        legacy = phonetic.replace(' ', '-')
        if legacy != phonetic:
            result = re.compile(re.escape(legacy), re.IGNORECASE).sub(canonical, result)

    def _replace(match: re.Match[str]) -> str:
        return denormalize_phonetic_word(match.group(0))

    return _WORD.sub(_replace, result)


def preprocess_debug_phonetic(text: str, *, reply_script: str = 'hinglish') -> dict[str, str]:
    """Stage breakdown for CLI / eval tooling."""
    phonetic = apply_phonetic_hyphens(text, reply_script=reply_script)
    restored = denormalize_phonetic_text(phonetic, reply_script=reply_script)
    return {
        'input': text,
        'phonetic': phonetic,
        'stt_restored': restored,
    }

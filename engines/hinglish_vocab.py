"""Load and clean Hinglish vocab CSVs for training and runtime exports."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from config import HINGLISH_VOCAB_DIR
from engines.hinglish_normalize import normalize_hinglish
from engines.stt_filters import is_phantom_stt_text, normalize_stt_text

_WORDS_CSV = 'hinglish_words.csv'
_CONVERSATIONS_CSV = 'hinglish_conversations.csv'

_LATIN_TOKEN = re.compile(r"^[A-Za-z][A-Za-z'\-]{1,40}$")
_HAS_DIGIT = re.compile(r'\d')
_URL_LIKE = re.compile(r'(https?://|www\.|\.com|\.au|\.in\b)', re.I)

_BUILTIN_PARTICLES = frozenset(
    {
        'aap',
        'aapko',
        'arre',
        'bhai',
        'boliye',
        'bolo',
        'haan',
        'hai',
        'hain',
        'hoon',
        'ji',
        'kripya',
        'kya',
        'kyun',
        'kyu',
        'main',
        'mein',
        'mera',
        'meri',
        'nahi',
        'nahin',
        'naam',
        'please',
        'sorry',
        'theek',
        'thoda',
        'tum',
        'tumhe',
        'yaar',
        'yeh',
    }
)


def vocab_dir() -> Path:
    return Path(HINGLISH_VOCAB_DIR)


def words_csv_path() -> Path:
    return vocab_dir() / _WORDS_CSV


def conversations_csv_path() -> Path:
    return vocab_dir() / _CONVERSATIONS_CSV


def is_clean_lexicon_token(word: str) -> bool:
    """True if token is a plausible romanized Hinglish/Hindi word."""
    cleaned = (word or '').strip()
    if not cleaned or len(cleaned) < 2:
        return False
    if _HAS_DIGIT.search(cleaned):
        return False
    if _URL_LIKE.search(cleaned):
        return False
    if not _LATIN_TOKEN.match(cleaned):
        return False
    if len(cleaned) > 24:
        return False
    return True


def clean_utterance(text: str) -> str | None:
    """Normalize and validate a training/conversation line."""
    prepared = normalize_hinglish(text or '')
    if not prepared or len(prepared.strip()) < 8:
        return None
    if is_phantom_stt_text(prepared):
        return None
    return prepared.strip()


@lru_cache(maxsize=1)
def _load_lexicon_rows() -> tuple[tuple[str, int], ...]:
    path = words_csv_path()
    if not path.is_file():
        return ()
    rows: list[tuple[str, int]] = []
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            word = row[0].strip()
            try:
                freq = int(row[1])
            except ValueError:
                freq = 1
            if is_clean_lexicon_token(word):
                rows.append((normalize_hinglish(word).lower(), freq))
    return tuple(rows)


@lru_cache(maxsize=1)
def _load_conversation_rows() -> tuple[tuple[str, str], ...]:
    path = conversations_csv_path()
    if not path.is_file():
        return ()
    rows: list[tuple[str, str]] = []
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            inp = (row.get('input') or '').strip()
            out = (row.get('output') or '').strip()
            if inp:
                rows.append(('input', inp))
            if out:
                rows.append(('output', out))
    return tuple(rows)


def iter_lexicon_words(*, min_freq: int = 1) -> list[tuple[str, int]]:
    seen: set[str] = set()
    out: list[tuple[str, int]] = []
    for word, freq in sorted(_load_lexicon_rows(), key=lambda x: (-x[1], x[0])):
        if freq < min_freq or word in seen:
            continue
        seen.add(word)
        out.append((word, freq))
    return out


def iter_conversation_utterances(*, dedupe: bool = True) -> list[str]:
    seen: set[str] = set()
    utterances: list[str] = []
    for _role, raw in _load_conversation_rows():
        cleaned = clean_utterance(raw)
        if not cleaned:
            continue
        key = normalize_stt_text(cleaned)
        if dedupe and key in seen:
            continue
        seen.add(key)
        utterances.append(cleaned)
    return utterances


def hinglish_particles(*, min_freq: int = 2, max_words: int = 120) -> frozenset[str]:
    """High-frequency function words suitable for stopword / name-parse lists."""
    particles = set(_BUILTIN_PARTICLES)
    for word, freq in iter_lexicon_words(min_freq=min_freq):
        if freq < min_freq:
            continue
        if len(word) <= 12:
            particles.add(word)
        if len(particles) >= max_words:
            break
    return frozenset(particles)


def build_whisper_vocab_prompt(*, max_chars: int = 400) -> str:
    """Sample Hinglish phrases for Whisper initial_prompt bias (token-limited)."""
    prefix = (
        'Hinglish conversation mixing Hindi and English in Latin script. '
        'Common words: '
    )
    parts: list[str] = [prefix]
    used = len(prefix)
    for word, _freq in iter_lexicon_words(min_freq=3)[:80]:
        chunk = f'{word}, '
        if used + len(chunk) > max_chars:
            break
        parts.append(chunk)
        used += len(chunk)
    for utterance in iter_conversation_utterances()[:20]:
        snippet = utterance[:60].rstrip() + '. '
        if used + len(snippet) > max_chars:
            break
        parts.append(snippet)
        used += len(snippet)
    return ''.join(parts).strip()


def build_normalize_variant_map(*, min_freq: int = 2) -> dict[str, str]:
    """Map common misspellings to normalized forms (identity for canonical tokens)."""
    mapping: dict[str, str] = {}
    for word, freq in iter_lexicon_words(min_freq=min_freq):
        if freq < min_freq:
            continue
        normalized = normalize_hinglish(word)
        if normalized and normalized != word:
            mapping[word] = normalized
        elif normalized:
            mapping.setdefault(normalized, normalized)
    return mapping


def vocab_stats() -> dict[str, int]:
    return {
        'lexicon_rows': len(_load_lexicon_rows()),
        'conversation_rows': len(_load_conversation_rows()),
        'clean_utterances': len(iter_conversation_utterances()),
        'particle_count': len(hinglish_particles()),
    }

"""Indian + English interview name list for Whisper bias and STT correction."""

from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import HINGLISH_VOCAB_DIR, _ROOT

_NAME_FILE = Path(HINGLISH_VOCAB_DIR) / 'interview_names.txt'
_CSV_FILE = Path(HINGLISH_VOCAB_DIR) / 'indian_male_names.csv'

# Common Whisper mis-hearings → canonical (checked before fuzzy index).
_NAME_ALIASES: dict[str, str] = {
    'awish': 'Ashish',
    'asheesh': 'Ashish',
    'aashis': 'Ashish',
    'ashis': 'Ashish',
    'asish': 'Ashish',
    'aayush': 'Aayush',
    'ayush': 'Ayush',
    'azush': 'Azush',
    'aleks': 'Alex',
}

_PREFIX_RE = re.compile(
    r'^(?:mr\.?|mrs\.?|ms\.?|dr\.?|shri\.?|smt\.?|kumari\.?|kumar\.?)\s+',
    re.IGNORECASE,
)
_NAME_TOKEN = re.compile(r"^[A-Za-z][A-Za-z'\-]{1,}$")
_NAME_CONTEXT = re.compile(
    r'(\b(?:my name is|i am|i\'m|this is|mera naam|main)\s+)([A-Za-z][A-Za-z\'\-]{1,})',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NameIndex:
    """In-memory indexes for O(1) exact lookup and small fuzzy candidate sets."""

    exact: dict[str, str]
    by_prefix2: dict[str, tuple[str, ...]]
    by_first: dict[str, tuple[str, ...]]
    priority: tuple[str, ...]
    total: int


def _name_paths() -> tuple[Path, Path]:
    txt = _NAME_FILE if _NAME_FILE.is_file() else _ROOT / 'data' / 'vocab' / 'interview_names.txt'
    csv_path = _CSV_FILE if _CSV_FILE.is_file() else _ROOT / 'data' / 'vocab' / 'indian_male_names.csv'
    return txt, csv_path


def _canonical_name(raw: str) -> str | None:
    token = (raw or '').strip().strip('.,!?')
    if not token or not _NAME_TOKEN.match(token):
        return None
    if token.islower():
        return token.title()
    return token


def _first_token_from_csv_cell(cell: str) -> str | None:
    cleaned = (cell or '').strip()
    if not cleaned:
        return None
    cleaned = _PREFIX_RE.sub('', cleaned)
    cleaned = re.split(r'[@/|,]', cleaned, maxsplit=1)[0].strip()
    parts = cleaned.split()
    if not parts:
        return None
    return _canonical_name(parts[0])


def _load_priority_names(path: Path) -> list[str]:
    if not path.is_file():
        return []
    names: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        name = line.strip()
        if not name or name.startswith('#'):
            continue
        canon = _canonical_name(name)
        if not canon:
            continue
        key = canon.lower()
        if key not in seen:
            seen.add(key)
            names.append(canon)
    return names


def _load_csv_tokens(path: Path) -> list[str]:
    if not path.is_file():
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    with path.open(encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            token = _first_token_from_csv_cell(row.get('name', ''))
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            tokens.append(token)
    return tokens


@lru_cache(maxsize=1)
def _get_index() -> NameIndex:
    txt_path, csv_path = _name_paths()
    priority = _load_priority_names(txt_path)
    csv_tokens = _load_csv_tokens(csv_path)

    exact: dict[str, str] = {}
    prefix2: dict[str, set[str]] = {}
    first: dict[str, set[str]] = {}

    def _register(name: str) -> None:
        key = name.lower()
        exact.setdefault(key, name)
        p2 = key[:2] if len(key) >= 2 else key
        prefix2.setdefault(p2, set()).add(name)
        first.setdefault(key[0], set()).add(name)

    for name in priority:
        _register(name)
    for name in csv_tokens:
        _register(name)

    if not exact:
        for name in _NAME_ALIASES.values():
            _register(name)

    by_prefix2 = {k: tuple(sorted(v)) for k, v in prefix2.items()}
    by_first = {k: tuple(sorted(v)) for k, v in first.items()}
    return NameIndex(
        exact=exact,
        by_prefix2=by_prefix2,
        by_first=by_first,
        priority=tuple(priority) if priority else tuple(exact.values())[:96],
        total=len(exact),
    )


@lru_cache(maxsize=1)
def load_interview_names() -> tuple[str, ...]:
    """Priority names for Whisper prompt and demos (not the full CSV set)."""
    return _get_index().priority


def whisper_names_prompt(max_names: int = 48) -> str:
    names = load_interview_names()
    chunk = ', '.join(names[:max_names])
    return f'Candidate names include: {chunk}.'


def _fuzzy_candidates(token: str, index: NameIndex) -> list[str]:
    low = token.lower()
    p2 = low[:2] if len(low) >= 2 else low[:1]
    bucket: set[str] = set(index.by_prefix2.get(p2, ()))
    if len(bucket) < 8 and low:
        bucket.update(index.by_first.get(low[0], ()))
    if not bucket:
        return []
    target_len = len(low)
    return sorted(
        n
        for n in bucket
        if abs(len(n) - target_len) <= 3
    )


def closest_name(token: str, *, cutoff: float = 0.72) -> str | None:
    raw = (token or '').strip().strip('.,!?')
    if not raw or not _NAME_TOKEN.match(raw):
        return None
    low = raw.lower()
    if low in _NAME_ALIASES:
        return _NAME_ALIASES[low]
    index = _get_index()
    if low in index.exact:
        return index.exact[low]
    candidates = _fuzzy_candidates(raw, index)
    if not candidates:
        return None
    match = difflib.get_close_matches(raw.title(), candidates, n=1, cutoff=cutoff)
    return match[0] if match else None


def correct_names_in_transcript(text: str) -> str:
    cleaned = (text or '').strip()
    if not cleaned:
        return ''

    def _fix_context(m: re.Match[str]) -> str:
        prefix, tok = m.group(1), m.group(2)
        return prefix + (closest_name(tok) or tok)

    out = _NAME_CONTEXT.sub(_fix_context, cleaned)

    words = out.split()
    if len(words) == 1:
        bare = words[0].strip('.,!?')
        fixed = closest_name(bare)
        if fixed:
            suffix = words[0][len(bare) :]
            return fixed + suffix
    return out

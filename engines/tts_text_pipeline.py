"""TTS text preprocessing: spell normalize, token classify, Devanagari transliteration."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from config import F5_HINGLISH_SCRIPT, HINGLISH_VOCAB_DIR, TTS_DEVANAGARI_SOURCE, TTS_HINGLISH_ROMAN, TTS_OUTPUT_SCRIPT
from engines.hinglish_normalize import normalize_hinglish
from engines.hinglish_vocab import hinglish_particles
from engines.llm_script_contract import validate_assistant_script
from engines.tts_pacing import add_speech_pauses

logger = logging.getLogger(__name__)

ReplyScript = Literal['en', 'hi', 'hinglish']
OutputScript = Literal['roman', 'devanagari']
TokenLang = Literal['en', 'hi', 'devanagari', 'punct']

_DEVANAGARI = re.compile(r'[\u0900-\u097F]+')
_LATIN_WORD = re.compile(r"^[A-Za-z][A-Za-z0-9'\-]*$")
_TOKEN_SPLIT = re.compile(r"(\s+|[\u0900-\u097F]+|[A-Za-z][A-Za-z0-9'\-]*|[^\w\s])")

_EN_PRESERVE = frozenset(
    {
        'api',
        'apis',
        'backend',
        'frontend',
        'react',
        'node',
        'python',
        'java',
        'javascript',
        'typescript',
        'docker',
        'kubernetes',
        'microservices',
        'database',
        'postgresql',
        'mongodb',
        'redis',
        'github',
        'gitlab',
        'devops',
        'ci',
        'cd',
        'rest',
        'graphql',
        'aws',
        'azure',
        'gcp',
        'linux',
        'windows',
        'android',
        'ios',
        'software',
        'engineer',
        'developer',
        'interview',
        'technical',
        'system',
        'design',
        'debugging',
        'deployment',
        'astra',
        'screen',
        'share',
        'camera',
        'welcome',
        'hello',
        'today',
        'role',
        'stack',
        'project',
        'experience',
        'resume',
        'team',
        'company',
        'work',
        'remote',
        'office',
        'deadline',
        'agile',
        'scrum',
        'jira',
        'slack',
        'zoom',
        'teams',
        'html',
        'css',
        'sql',
        'nosql',
        'http',
        'https',
        'json',
        'xml',
        'yaml',
        'nginx',
        'kafka',
        'rabbitmq',
        'celery',
        'django',
        'flask',
        'fastapi',
        'spring',
        'angular',
        'vue',
        'nextjs',
        'express',
        'tensorflow',
        'pytorch',
        'ml',
        'ai',
        'llm',
        'gpt',
        'openai',
    }
)

_HINDI_SUFFIXES = (
    'hai',
    'hain',
    'hoon',
    'ho',
    'kiya',
    'karte',
    'karta',
    'karti',
    'karne',
    'kar',
    'kiye',
    'gaya',
    'gayi',
    'gaye',
    'raha',
    'rahi',
    'rahe',
    'wala',
    'wali',
    'wale',
    'iyega',
    'iyegi',
    'iyenge',
    'unga',
    'ungi',
    'enge',
)

_normalize_mtime: float = 0.0
_particles_mtime: float = 0.0


@dataclass
class TokenInfo:
    raw: str
    normalized: str
    lang: TokenLang
    output: str


def _vocab_dir() -> Path:
    return Path(HINGLISH_VOCAB_DIR)


def _load_generated_normalize_map() -> dict[str, str]:
    global _normalize_mtime
    path = _vocab_dir() / 'hinglish_normalize.generated.json'
    if not path.is_file():
        return {}
    mtime = path.stat().st_mtime
    if mtime != _normalize_mtime:
        _load_generated_normalize_map_cached.cache_clear()
        _normalize_mtime = mtime
    return _load_generated_normalize_map_cached()


@lru_cache(maxsize=1)
def _load_generated_normalize_map_cached() -> dict[str, str]:
    path = _vocab_dir() / 'hinglish_normalize.generated.json'
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return {str(k).lower(): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning('Failed to load normalize map: %s', exc)
        return {}


def _load_extra_particles() -> frozenset[str]:
    global _particles_mtime
    path = _vocab_dir() / 'hinglish_particles.txt'
    if not path.is_file():
        return frozenset()
    mtime = path.stat().st_mtime
    if mtime != _particles_mtime:
        _load_extra_particles_cached.cache_clear()
        _particles_mtime = mtime
    return _load_extra_particles_cached()


@lru_cache(maxsize=1)
def _load_extra_particles_cached() -> frozenset[str]:
    path = _vocab_dir() / 'hinglish_particles.txt'
    if not path.is_file():
        return frozenset()
    try:
        return frozenset(
            line.strip().lower()
            for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip()
        )
    except OSError:
        return frozenset()


def _all_particles() -> frozenset[str]:
    return hinglish_particles() | _load_extra_particles()


def _apply_generated_map(word: str) -> str:
    lower = word.lower()
    generated = _load_generated_normalize_map()
    mapped = generated.get(lower)
    if mapped:
        if word[0].isupper() and mapped:
            return mapped[0].upper() + mapped[1:]
        return mapped
    return word


def _looks_like_hindi_latin(word: str) -> bool:
    lower = word.lower()
    if lower in _EN_PRESERVE:
        return False
    if lower in _all_particles():
        return True
    if lower in _load_generated_normalize_map():
        return True
    if any(lower.endswith(sfx) for sfx in _HINDI_SUFFIXES):
        return True
    if re.search(r'(kh|gh|chh|dh|bh|sh|th|ph|aa|ee|oo|yaar|bhai|ji)$', lower):
        return True
    return False


def _classify_token(word: str, *, reply_script: ReplyScript) -> TokenLang:
    if _DEVANAGARI.search(word):
        return 'devanagari'
    if not _LATIN_WORD.match(word):
        return 'punct'
    lower = word.lower()
    if lower in _EN_PRESERVE:
        return 'en'
    if word.isupper() and len(word) >= 2:
        return 'en'
    if reply_script == 'en':
        return 'en'
    if _looks_like_hindi_latin(word):
        return 'hi'
    if reply_script in ('hi', 'hinglish') and len(lower) <= 12:
        return 'hi'
    return 'en'


def _transliterate_hi_word(word: str) -> str:
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
    except ImportError:
        logger.warning('indic-transliteration not installed; keeping roman Hindi')
        return word
    lower = word.lower()
    try:
        dev = transliterate(lower, sanscript.ITRANS, sanscript.DEVANAGARI)
    except Exception:
        return word
    if not dev or dev == lower:
        return word
    if word[0].isupper():
        return dev
    return dev


def _resolve_output_script(
    *,
    reply_script: ReplyScript,
    engine: str,
    explicit: OutputScript | None = None,
) -> OutputScript:
    if explicit:
        return explicit
    if reply_script == 'en':
        return 'roman'
    if reply_script in ('hi', 'hinglish'):
        if reply_script == 'hinglish' and TTS_HINGLISH_ROMAN:
            return 'roman'
        if TTS_OUTPUT_SCRIPT == 'devanagari':
            return 'devanagari'
        if engine == 'f5' and F5_HINGLISH_SCRIPT == 'devanagari':
            return 'devanagari'
        return 'roman'
    return 'roman'


def tokenize_for_tts(text: str, *, reply_script: ReplyScript = 'en') -> list[TokenInfo]:
    normalized = normalize_hinglish(text)
    if not normalized:
        return []
    tokens: list[TokenInfo] = []
    for part in _TOKEN_SPLIT.findall(normalized):
        if not part or part.isspace():
            continue
        if _DEVANAGARI.fullmatch(part):
            tokens.append(
                TokenInfo(raw=part, normalized=part, lang='devanagari', output=part)
            )
            continue
        if not _LATIN_WORD.match(part):
            tokens.append(TokenInfo(raw=part, normalized=part, lang='punct', output=part))
            continue
        norm = _apply_generated_map(part)
        lang = _classify_token(norm, reply_script=reply_script)
        tokens.append(TokenInfo(raw=part, normalized=norm, lang=lang, output=norm))
    return tokens


def to_devanagari_mixed(text: str, *, reply_script: ReplyScript = 'hinglish') -> str:
    tokens = tokenize_for_tts(text, reply_script=reply_script)
    parts: list[str] = []
    for tok in tokens:
        if tok.lang == 'punct':
            parts.append(tok.output)
        elif tok.lang == 'devanagari':
            parts.append(tok.output)
        elif tok.lang == 'hi':
            parts.append(_transliterate_hi_word(tok.normalized))
        else:
            parts.append(tok.normalized)
    merged = ''
    for part in parts:
        if not part:
            continue
        if merged and part in '.,!?;:)]}\'"':
            merged += part
        elif merged and merged[-1] in '([{"\'':
            merged += part
        elif merged:
            merged += ' ' + part
        else:
            merged = part
    return re.sub(r'\s+([.,!?;:])', r'\1', merged).strip()


def split_for_f5_chunks(text: str) -> list[str]:
    """Split on sentence boundaries before F5 chunk_text."""
    cleaned = (text or '').strip()
    if not cleaned:
        return []
    parts = re.split(r'(?<=[।.?!])\s+', cleaned)
    return [p.strip() for p in parts if p.strip()]


def normalize_mixed_script(text: str) -> str:
    """Normalize Latin segments only; preserve Devanagari blocks unchanged."""
    if not text:
        return ''
    parts: list[str] = []
    for segment in re.split(r'([\u0900-\u097F]+)', text):
        if not segment or not segment.strip():
            continue
        if _DEVANAGARI.search(segment):
            parts.append(segment.strip())
        else:
            normalized = normalize_hinglish(segment)
            if normalized:
                parts.append(normalized)
    merged = ' '.join(parts)
    return re.sub(r'\s+', ' ', merged).strip()


def prepare_text_for_tts(
    text: str,
    *,
    reply_script: ReplyScript | None = None,
    engine: str = 'f5',
    output_script: OutputScript | None = None,
    session_lang: str | None = None,
    llm_compliant: bool | None = None,
) -> str:
    """Full pipeline entry: normalize spelling and optionally transliterate to Devanagari."""
    import time

    started = time.perf_counter()
    script: ReplyScript = reply_script if reply_script in ('en', 'hi', 'hinglish') else 'en'  # type: ignore[assignment]
    mode = _resolve_output_script(
        reply_script=script,
        engine=engine,
        explicit=output_script,
    )
    if mode == 'devanagari' and script in ('hi', 'hinglish'):
        use_llm_fast = TTS_DEVANAGARI_SOURCE == 'llm'
        compliant = llm_compliant
        if compliant is None and use_llm_fast:
            from engines.llm_script_contract import effective_session_lang

            effective = effective_session_lang(session_lang, script)  # type: ignore[arg-type]
            compliant = validate_assistant_script(text, effective)
        if use_llm_fast and compliant:
            result = normalize_mixed_script(text)
        else:
            result = to_devanagari_mixed(text, reply_script=script)
        logger.debug(
            'tts_preprocess_ms=%.2f fast_path=%s',
            (time.perf_counter() - started) * 1000,
            use_llm_fast and compliant,
        )
        return add_speech_pauses(result, reply_script=script)
    result = normalize_hinglish(text)
    return add_speech_pauses(result, reply_script=script)


def prepare_text_for_f5_tts(
    text: str,
    *,
    reply_script: ReplyScript | None = None,
) -> str:
    """Backward-compatible wrapper used by F5 engine."""
    script: ReplyScript = reply_script or 'en'
    if script not in ('en', 'hi', 'hinglish'):
        script = 'en'
    return prepare_text_for_tts(text, reply_script=script, engine='f5')


def preprocess_debug(text: str, *, reply_script: ReplyScript = 'hinglish') -> dict:
    """Return pipeline stages for CLI / eval tooling."""
    normalized = normalize_hinglish(text)
    tokens = tokenize_for_tts(text, reply_script=reply_script)
    devanagari = to_devanagari_mixed(text, reply_script=reply_script)
    return {
        'original': text,
        'normalized': normalized,
        'devanagari': devanagari,
        'reply_script': reply_script,
        'tokens': [
            {
                'raw': t.raw,
                'normalized': t.normalized,
                'lang': t.lang,
                'output': t.output,
            }
            for t in tokens
        ],
    }

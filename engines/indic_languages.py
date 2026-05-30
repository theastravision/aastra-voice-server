"""Indian languages metadata — script, Whisper codes, and TTS routing in this stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TtsPipeline = Literal['en', 'hi']  # Parler caption routing (en / hi)


@dataclass(frozen=True)
class IndicLanguageInfo:
    code: str
    name: str
    script: str
    whisper_iso: str
    tts_pipeline: TtsPipeline
    notes: str


# Languages commonly written in Devanagari (same script, different grammar/vocab).
DEVANAGARI_INDIAN_LANGUAGES: tuple[IndicLanguageInfo, ...] = (
    IndicLanguageInfo('hi', 'Hindi', 'Devanagari', 'hi', 'hi', 'Fully supported via Indic Parler-TTS.'),
    IndicLanguageInfo(
        'mr',
        'Marathi',
        'Devanagari',
        'mr',
        'hi',
        'STT: Whisper mr. TTS: Hindi pipeline only (approximate pronunciation).',
    ),
    IndicLanguageInfo(
        'ne',
        'Nepali',
        'Devanagari',
        'ne',
        'hi',
        'STT: Whisper ne. TTS: Hindi pipeline fallback.',
    ),
    IndicLanguageInfo(
        'sa',
        'Sanskrit',
        'Devanagari',
        'sa',
        'hi',
        'STT possible; TTS poor without dedicated training.',
    ),
    IndicLanguageInfo(
        'mai',
        'Maithili',
        'Devanagari',
        'mai',
        'hi',
        'Needs fine-tuned STT/TTS for quality.',
    ),
    IndicLanguageInfo(
        'doi',
        'Dogri',
        'Devanagari',
        'doi',
        'hi',
        'Official Devanagari; limited OSS TTS.',
    ),
    IndicLanguageInfo('en', 'English', 'Latin', 'en', 'en', 'Kokoro af_bella.'),
    IndicLanguageInfo(
        'hinglish',
        'Hinglish',
        'Mixed',
        'hi',
        'hinglish',
        'Code-mixed EN+HI; normalized via hinglish_normalize.py for F5-TTS.',
    ),
)

_BY_WHISPER = {x.whisper_iso: x for x in DEVANAGARI_INDIAN_LANGUAGES}
_BY_CODE = {x.code: x for x in DEVANAGARI_INDIAN_LANGUAGES}


def lookup_by_whisper(detected: str | None) -> IndicLanguageInfo | None:
    if not detected:
        return None
    key = detected.lower().split('-')[0]
    return _BY_WHISPER.get(key) or _BY_CODE.get(key)


def tts_pipeline_for_detected(detected: str | None, *, reply_script: str = 'hi') -> str:
    """Map detected language to Kokoro route: en | hi | hinglish."""
    if reply_script == 'hinglish':
        return 'hinglish'
    info = lookup_by_whisper(detected)
    if info:
        if info.code == 'en':
            return 'en'
        if info.code == 'hinglish':
            return 'hinglish'
        return 'hi'
    return 'hi' if reply_script == 'hi' else 'en'

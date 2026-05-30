"""Lightweight Hinglish romanization normalizer for F5-TTS character tokenizer."""

from __future__ import annotations

import re
import unicodedata

_STRIP_MARKDOWN = re.compile(r'[*_~`]')
_LATIN_WORD = re.compile(r'[A-Za-z]+')
_REPEAT_CHARS = re.compile(r'(.)\1{2,}')

_HINGLISH_MAP: dict[str, str] = {
    'accha': 'achha',
    'acha': 'achha',
    'achaa': 'achha',
    'achhaa': 'achha',
    'theek': 'theek',
    'thik': 'theek',
    'tik': 'theek',
    'thikhai': 'theek hai',
    'theekhai': 'theek hai',
    'samaj': 'samajh',
    'samjha': 'samajh',
    'samjhe': 'samajh',
    'samajhna': 'samajhna',
    'samajh': 'samajh',
    'samajhte': 'samajhte',
    'kaam': 'kaam',
    'kam': 'kaam',
    'kamm': 'kaam',
    'nahi': 'nahi',
    'nahin': 'nahi',
    'nai': 'nahi',
    'nhi': 'nahi',
    'haan': 'haan',
    'han': 'haan',
    'hain': 'hain',
    'hai': 'hai',
    'hainn': 'hain',
    'kya': 'kya',
    'kyaa': 'kya',
    'kyun': 'kyun',
    'kyu': 'kyun',
    'kyon': 'kyun',
    'batao': 'batao',
    'bataiye': 'bataiye',
    'bataye': 'bataiye',
    'bata': 'bata',
    'bolo': 'bolo',
    'boliye': 'boliye',
    'shuru': 'shuru',
    'suruaat': 'shuruaat',
    'shuruaat': 'shuruaat',
    'experience': 'experience',
    'experiance': 'experience',
    'project': 'project',
    'projekt': 'project',
    'interview': 'interview',
    'intarview': 'interview',
    'technical': 'technical',
    'teknikal': 'technical',
    'problem': 'problem',
    'problm': 'problem',
    'solution': 'solution',
    'sahi': 'sahi',
    'sahii': 'sahi',
    'galat': 'galat',
    'galt': 'galat',
    'achhe': 'achhe',
    'acche': 'achhe',
    'bahut': 'bahut',
    'bohot': 'bahut',
    'boht': 'bahut',
    'thoda': 'thoda',
    'thodi': 'thodi',
    'zyada': 'zyada',
    'jada': 'zyada',
    'zyadaa': 'zyada',
    'mein': 'mein',
    'main': 'mein',
    'mai': 'mein',
    'mujhe': 'mujhe',
    'mujhko': 'mujhe',
    'aap': 'aap',
    'aapko': 'aapko',
    'tum': 'tum',
    'tumhe': 'tumhe',
    'hum': 'hum',
    'humko': 'humko',
    'chalo': 'chalo',
    'chaliye': 'chaliye',
    'chalein': 'chalein',
    'dekho': 'dekho',
    'dekhiye': 'dekhiye',
    'dekhte': 'dekhte',
    'socho': 'socho',
    'sochiye': 'sochiye',
    'lagta': 'lagta',
    'lagti': 'lagti',
    'lagte': 'lagte',
}


def _normalize_latin_token(word: str) -> str:
    lower = word.lower()
    mapped = _HINGLISH_MAP.get(lower)
    if mapped:
        if word[0].isupper() and mapped:
            return mapped[0].upper() + mapped[1:]
        return mapped
    collapsed = _REPEAT_CHARS.sub(r'\1', lower)
    if word[0].isupper() and collapsed:
        return collapsed[0].upper() + collapsed[1:]
    return collapsed if word.islower() else word


def prepare_text_for_f5_tts(text: str, *, reply_script: str | None = None) -> str:
    """Delegate to tts_text_pipeline (Devanagari or roman per config)."""
    from engines.tts_text_pipeline import prepare_text_for_f5_tts as _prep

    script = reply_script if reply_script in ('en', 'hi', 'hinglish') else 'en'
    return _prep(text, reply_script=script)  # type: ignore[arg-type]


def normalize_hinglish(text: str) -> str:
    """Sanitize LLM text before F5-TTS to reduce spelling stutter."""
    if not text:
        return ''
    cleaned = unicodedata.normalize('NFKC', text)
    cleaned = _STRIP_MARKDOWN.sub('', cleaned)

    def _replace_word(match: re.Match[str]) -> str:
        return _normalize_latin_token(match.group(0))

    cleaned = _LATIN_WORD.sub(_replace_word, cleaned)
    return cleaned.strip()

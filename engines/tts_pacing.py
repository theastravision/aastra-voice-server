"""Insert natural pause markers for Hinglish/Hindi TTS (F5 voice clone pacing)."""

from __future__ import annotations

import re

from config import TTS_HINGLISH_PACE_PAUSES, TTS_HINGLISH_PAUSE_STYLE

_DEVANAGARI = re.compile(r'[\u0900-\u097F]')
_LATIN = re.compile(r'[A-Za-z]')
# Latin run then Devanagari, or Devanagari then Latin (mixed-script breath)
_SCRIPT_BOUNDARY = re.compile(
    r'([\u0900-\u097F]+)\s+([A-Za-z])|([A-Za-z])\s+([\u0900-\u097F])',
)
# Comma not already followed by ellipsis
_COMMA_PAUSE = re.compile(r',(?!\s*\.{2,3})')
# Clause connectors in roman Hinglish — slight pause helps Swara/F5 pacing
_CLAUSE_PAUSE = re.compile(
    r'\s+(aur|ki|ke|ko|mein|main|par|pe|se|tab|jab|toh|to|ya)\s+',
    re.IGNORECASE,
)
# Story mode: comma → full breath ellipsis
_STORY_COMMA = re.compile(r',\s*')
# List-like place names in roman Hinglish narratives
_PLACE_LIST = re.compile(
    r'\b(jo\s+)(gaon|gaanv|shehar|she-har|desh)\b',
    re.IGNORECASE,
)
_PLACE_MID = re.compile(
    r'\b(gaon|gaanv|shehar|she-har)\s+(aur\s+)?(desh)\b',
    re.IGNORECASE,
)
# Clause tails that benefit from a breath before synthesis
_CLAUSE_TAIL = re.compile(
    r'\b(aur\s+aisi|ke\s+logon\s+ki|bana\s+sake)\b',
    re.IGNORECASE,
)
_ELLIPSIS_RUN = re.compile(r'(\s*\.{3}\s*)+')


def _collapse_ellipsis(text: str) -> str:
    spaced = _ELLIPSIS_RUN.sub(' ... ', text)
    return re.sub(r'\s+', ' ', spaced).strip()


def _add_standard_pauses(text: str, *, reply_script: str) -> str:
    def _boundary(m: re.Match[str]) -> str:
        if m.group(1) and m.group(2):
            return f'{m.group(1)} ... {m.group(2)}'
        return f'{m.group(3)} ... {m.group(4)}'

    paced = _SCRIPT_BOUNDARY.sub(_boundary, text)
    paced = _COMMA_PAUSE.sub(', ...', paced)
    if reply_script == 'hinglish' and not _DEVANAGARI.search(paced):
        paced = _CLAUSE_PAUSE.sub(r' ... \1 ', paced)
    return _collapse_ellipsis(paced)


def _add_story_pauses(text: str, *, reply_script: str) -> str:
    paced = _add_standard_pauses(text, reply_script=reply_script)
    # Commas become standalone breaths (not ", ...")
    paced = _STORY_COMMA.sub(' ... ', paced)

    def _place_start(m: re.Match[str]) -> str:
        return f'{m.group(1)} ... {m.group(2)}'

    paced = _PLACE_LIST.sub(_place_start, paced)

    def _place_mid(m: re.Match[str]) -> str:
        mid = f' ... {m.group(2)}' if m.group(2) else ''
        return f'{m.group(1)}{mid} ... {m.group(3)}'

    paced = _PLACE_MID.sub(_place_mid, paced)
    paced = _CLAUSE_TAIL.sub(r' ... \1', paced)
    return _collapse_ellipsis(paced)


def add_speech_pauses(text: str, *, reply_script: str = 'hinglish') -> str:
    """
    Add ellipsis pause cues so F5/Swara does not rush through Hinglish clauses.
    Safe for roman or mixed-script LLM output.
    """
    if not TTS_HINGLISH_PACE_PAUSES or reply_script not in ('hi', 'hinglish'):
        return (text or '').strip()

    cleaned = (text or '').strip()
    if not cleaned:
        return cleaned

    style = TTS_HINGLISH_PAUSE_STYLE
    if style == 'story':
        return _add_story_pauses(cleaned, reply_script=reply_script)
    return _add_standard_pauses(cleaned, reply_script=reply_script)

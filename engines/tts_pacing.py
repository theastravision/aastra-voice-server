"""Insert natural pause markers for Hinglish/Hindi TTS (F5 voice clone pacing)."""

from __future__ import annotations

import re

from config import TTS_HINGLISH_PACE_PAUSES

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

    # Mixed Devanagari ↔ Latin boundaries
    def _boundary(m: re.Match[str]) -> str:
        if m.group(1) and m.group(2):
            return f'{m.group(1)} ... {m.group(2)}'
        return f'{m.group(3)} ... {m.group(4)}'

    paced = _SCRIPT_BOUNDARY.sub(_boundary, cleaned)
    # Commas → brief pause (primary "breathing room" cue)
    paced = _COMMA_PAUSE.sub(', ...', paced)
    # Roman clause connectors (light touch — skip if already has ellipsis nearby)
    if reply_script == 'hinglish' and not _DEVANAGARI.search(paced):
        paced = _CLAUSE_PAUSE.sub(r' ... \1 ', paced)

    paced = re.sub(r'(\.{3}\s*){2,}', ' ... ', paced)
    paced = re.sub(r'\s+', ' ', paced).strip()
    return paced

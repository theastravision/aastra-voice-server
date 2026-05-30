"""Hindi/Hinglish LLM token buffer for MeloTTS — flush on strong sentence boundaries only."""

from __future__ import annotations

import re

_STRIP_MARKDOWN = re.compile(r'[*_~`#]')
_STRIP_BRACKETS = re.compile(r'[\[\](){}]')
_STRONG_BOUNDARY = re.compile(r'([।.!?])|\n+')
_MAX_CHARS_BEFORE_WEAK_FLUSH = 120


def _clean_phrase(text: str) -> str:
    cleaned = _STRIP_MARKDOWN.sub('', text)
    cleaned = _STRIP_BRACKETS.sub('', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()


class HindiPhraseBuffer:
    """Accumulate LLM tokens until a complete Hindi/Hinglish sentence is ready for MeloTTS."""

    def __init__(self) -> None:
        self.buffer = ''

    def push(self, token: str) -> list[str]:
        self.buffer += token
        chunks: list[str] = []

        if '<' in self.buffer[-8:]:
            return chunks

        while True:
            match = _STRONG_BOUNDARY.search(self.buffer)
            if match:
                split_at = match.end()
                chunk = _clean_phrase(self.buffer[:split_at])
                self.buffer = self.buffer[split_at:].lstrip()
                if chunk:
                    chunks.append(chunk)
                continue

            if len(self.buffer) >= _MAX_CHARS_BEFORE_WEAK_FLUSH:
                weak = self._weak_flush()
                if weak:
                    chunks.append(weak)
                break
            break

        return chunks

    def _weak_flush(self) -> str:
        """Flush at last space when buffer grows too long without a strong boundary."""
        text = self.buffer.strip()
        if not text:
            self.buffer = ''
            return ''
        last_space = text.rfind(' ')
        if last_space <= 0:
            chunk = _clean_phrase(text)
            self.buffer = ''
            return chunk
        chunk = _clean_phrase(text[:last_space])
        self.buffer = text[last_space + 1 :].lstrip()
        return chunk

    def flush(self) -> str:
        chunk = _clean_phrase(self.buffer.strip())
        self.buffer = ''
        return chunk

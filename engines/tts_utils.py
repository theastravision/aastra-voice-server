"""Shared TTS text splitting and audio export helpers."""

from __future__ import annotations

import io
import re
from typing import Any

_MAX_CHUNK_CHARS = 200
_SENTENCE_SPLIT = re.compile(r'(?<=[।.!?])\s+|\n+')
_SPEAKABLE = re.compile(r'[\w\u0900-\u097F]', re.UNICODE)


def is_speakable_text(text: str) -> bool:
    """True if phrase has enough speakable characters for TTS."""
    cleaned = (text or '').strip()
    if isinstance(cleaned, bytes):
        cleaned = cleaned.decode('utf-8', errors='ignore').strip()
    return len(cleaned) >= 2 and bool(_SPEAKABLE.search(cleaned))


def split_tts_sentences(text: str) -> list[str]:
    """Split long text into speakable chunks for smoother TTS."""
    cleaned = (text or '').strip()
    if not cleaned:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(cleaned) if p.strip()]
    if not parts:
        parts = [cleaned]
    chunks: list[str] = []
    for part in parts:
        if len(part) <= _MAX_CHUNK_CHARS:
            chunks.append(part)
            continue
        words = part.split()
        buf: list[str] = []
        length = 0
        for word in words:
            add = len(word) + (1 if buf else 0)
            if length + add > _MAX_CHUNK_CHARS and buf:
                chunks.append(' '.join(buf))
                buf = [word]
                length = len(word)
            else:
                buf.append(word)
                length += add
        if buf:
            chunks.append(' '.join(buf))
    return chunks


def ensure_pcm_s16le_bytes(data: Any) -> bytes | None:
    """Coerce TTS output to raw PCM bytes for WebSocket send_bytes."""
    if data is None:
        return None
    if isinstance(data, bytes):
        return data if data else None
    if isinstance(data, bytearray):
        return bytes(data) if data else None
    if isinstance(data, memoryview):
        b = data.tobytes()
        return b if b else None
    try:
        import numpy as np

        if isinstance(data, np.ndarray):
            arr = np.asarray(data).squeeze()
            if arr.size == 0:
                return None
            if arr.dtype == np.int16:
                return arr.tobytes()
            arr = np.clip(arr.astype(np.float32), -1.0, 1.0)
            return (arr * 32767).astype(np.int16).tobytes()
    except ImportError:
        pass
    if isinstance(data, (list, tuple)) and data:
        return ensure_pcm_s16le_bytes(data[0])
    return None


def wav_to_mp3(wav_bytes: bytes) -> bytes:
    from pydub import AudioSegment

    segment = AudioSegment.from_wav(io.BytesIO(wav_bytes))
    out = io.BytesIO()
    segment.export(out, format='mp3', bitrate='128k')
    return out.getvalue()


def pcm_s16le_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw mono PCM s16le in a WAV container."""
    import struct

    data = pcm or b''
    n = len(data)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + n,
        b'WAVE',
        b'fmt ',
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b'data',
        n,
    )
    return header + data

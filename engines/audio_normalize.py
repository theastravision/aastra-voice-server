"""PCM s16le peak normalization before STT."""

from __future__ import annotations

import io
import struct


def normalize_pcm_s16le(pcm: bytes, *, target_dbfs: float = -3.0) -> bytes:
    """Boost quiet mic audio toward target_dbfs (peak). Returns input unchanged if silent."""
    if not pcm or len(pcm) < 4:
        return pcm
    try:
        from pydub import AudioSegment

        wav = _pcm_to_wav(pcm)
        audio = AudioSegment.from_file(io.BytesIO(wav), format='wav')
        if audio.max_dBFS <= -60:
            return pcm
        if audio.max_dBFS < target_dbfs:
            audio = audio.apply_gain(target_dbfs - audio.max_dBFS)
        buf = io.BytesIO()
        audio.export(buf, format='wav')
        return _wav_to_pcm(buf.getvalue())
    except ImportError:
        return _normalize_numpy(pcm, target_dbfs=target_dbfs)


def _normalize_numpy(pcm: bytes, *, target_dbfs: float) -> bytes:
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return pcm
    peak = float(np.max(np.abs(samples)))
    if peak < 1.0:
        return pcm
    target_peak = 32767.0 * (10 ** (target_dbfs / 20.0))
    gain = target_peak / peak
    if gain <= 1.0:
        return pcm
    boosted = np.clip(samples * gain, -32768, 32767).astype(np.int16)
    return boosted.tobytes()


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    n = len(pcm)
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
    return header + pcm


def _wav_to_pcm(wav: bytes) -> bytes:
    if len(wav) <= 44:
        return b''
    return wav[44:]

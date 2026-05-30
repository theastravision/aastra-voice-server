"""Convert uploaded browser audio to 16 kHz mono WAV for Whisper."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioDecodeError(Exception):
    """Raised when ffmpeg cannot decode the uploaded audio."""


def bytes_to_wav_path(audio_bytes: bytes, *, suffix: str = '.webm') -> str:
    """Write bytes to a temp file and transcode to 16 kHz mono WAV. Returns WAV path."""
    if not audio_bytes or len(audio_bytes) < 256:
        raise AudioDecodeError('Audio clip is too short or empty.')
    if shutil.which('ffmpeg') is None:
        raise AudioDecodeError('ffmpeg is not installed on this server.')

    suffix = suffix if suffix.startswith('.') else f'.{suffix}'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(audio_bytes)
        src_path = src.name

    wav_path = src_path + '.wav'
    try:
        proc = subprocess.run(
            [
                'ffmpeg',
                '-y',
                '-hide_banner',
                '-loglevel',
                'error',
                '-i',
                src_path,
                '-ar',
                '16000',
                '-ac',
                '1',
                '-f',
                'wav',
                wav_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0 or not Path(wav_path).is_file():
            detail = (proc.stderr or proc.stdout or 'unknown ffmpeg error').strip()
            logger.warning('ffmpeg decode failed: %s', detail[:500])
            raise AudioDecodeError('Could not decode audio; speak again.')
        return wav_path
    finally:
        Path(src_path).unlink(missing_ok=True)

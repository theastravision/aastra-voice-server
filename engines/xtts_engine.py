"""Coqui XTTS-v2 inference for Hindi/Hinglish with Astra voice clone."""

from __future__ import annotations

import io
import logging
import threading
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from config import (
    TTS_OUTPUT_FORMAT,
    XTTS_DEVICE,
    XTTS_LANGUAGE,
    XTTS_MODEL,
    XTTS_SPEAKER_WAV,
)
from engines.tts_text_pipeline import prepare_text_for_tts
from engines.tts_utils import ensure_pcm_s16le_bytes, wav_to_mp3
from engines.voice_registry import VoiceProfile, get_default_voice_id, get_voice

logger = logging.getLogger(__name__)

_manager: XTTSInferenceManager | None = None
_manager_lock = threading.Lock()
_import_error: str | None = None


def xtts_available() -> bool:
    global _import_error
    if _import_error is not None:
        return False
    try:
        from TTS.api import TTS  # noqa: F401

        return True
    except ImportError as exc:
        _import_error = str(exc)
        return False


def _resolve_device() -> str:
    if XTTS_DEVICE and XTTS_DEVICE != 'auto':
        return XTTS_DEVICE
    try:
        import torch

        if torch.cuda.is_available():
            return 'cuda'
    except ImportError:
        pass
    return 'cpu'


def _speaker_wav_for_voice(voice_id: str | None) -> str:
    profile = get_voice(voice_id or get_default_voice_id())
    if profile and profile.ref_audio_path().is_file():
        return str(profile.ref_audio_path().resolve())
    fallback = Path(XTTS_SPEAKER_WAV)
    if fallback.is_file():
        return str(fallback.resolve())
    raise FileNotFoundError(
        f'XTTS speaker WAV not found: {XTTS_SPEAKER_WAV}. '
        'Run: python scripts/setup_ref_audio.py --force'
    )


class XTTSInferenceManager:
    """Lazy-load Coqui XTTS-v2 and synthesize with reference voice clone."""

    def __init__(self) -> None:
        if not xtts_available():
            raise RuntimeError(
                'coqui-tts not installed. Run: bash scripts/install-xtts.sh'
            )
        from TTS.api import TTS

        device = _resolve_device()
        logger.info('Loading XTTS model=%s device=%s', XTTS_MODEL, device)
        self._tts = TTS(XTTS_MODEL).to(device)
        self._device = device
        self._sample_rate = 24000
        self._active_voice_id = get_default_voice_id()
        self._inference_lock = threading.Lock()

    def set_active_voice(self, voice_id: str | None) -> None:
        self._active_voice_id = voice_id or get_default_voice_id()

    def synthesize_stream_sync(
        self,
        text: str,
        *,
        reply_script: str | None = None,
    ) -> Iterator[tuple[bytes, int]]:
        cleaned = prepare_text_for_tts(
            text,
            reply_script=reply_script if reply_script in ('en', 'hi', 'hinglish') else 'hinglish',  # type: ignore[arg-type]
            engine='xtts',
            output_script='devanagari',
        )
        if not cleaned:
            return

        speaker_wav = _speaker_wav_for_voice(self._active_voice_id)
        lang = XTTS_LANGUAGE if reply_script in ('hi', 'hinglish', None) else 'en'

        with self._inference_lock:
            wav = self._tts.tts(
                text=cleaned,
                speaker_wav=speaker_wav,
                language=lang,
            )

        if wav is None:
            return
        audio = np.asarray(wav, dtype=np.float32)
        pcm = ensure_pcm_s16le_bytes(audio)
        if pcm:
            yield pcm, self._sample_rate

    def synthesize_wav_bytes(
        self,
        text: str,
        *,
        reply_script: str | None = None,
    ) -> tuple[bytes, str]:
        chunks: list[bytes] = []
        sr = self._sample_rate
        for pcm, rate in self.synthesize_stream_sync(text, reply_script=reply_script):
            chunks.append(pcm)
            sr = rate
        if not chunks:
            return b'', 'audio/wav'

        import soundfile as sf

        audio = np.frombuffer(b''.join(chunks), dtype=np.int16).astype(np.float32) / 32767.0
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format='WAV', subtype='PCM_16')
        wav_bytes = buf.getvalue()
        if TTS_OUTPUT_FORMAT == 'mp3':
            return wav_to_mp3(wav_bytes), 'audio/mpeg'
        return wav_bytes, 'audio/wav'


def get_manager() -> XTTSInferenceManager:
    global _manager
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is None:
            _manager = XTTSInferenceManager()
    return _manager


def synthesize_audio(
    text: str,
    *,
    reply_script: str | None = None,
    voice: str = 'astra',
    lang: str | None = None,
) -> tuple[bytes, str]:
    del lang
    mgr = get_manager()
    mgr.set_active_voice(voice)
    return mgr.synthesize_wav_bytes(text, reply_script=reply_script)

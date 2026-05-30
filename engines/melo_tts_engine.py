"""MeloTTS Engine integration for Hindi and Hinglish TTS."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from threading import Lock

import soundfile as sf
import torch

from config import MELOTTS_DEVICE, MELOTTS_SPEAKER, MELOTTS_SPEED
from engines.tts_utils import ensure_pcm_s16le_bytes

logger = logging.getLogger(__name__)

_manager: MeloTTSManager | None = None
_manager_lock = Lock()


def get_manager() -> MeloTTSManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = MeloTTSManager()
    return _manager


def warmup() -> None:
    """Load EN model and resolve speaker at startup."""
    mgr = get_manager()
    model = mgr._get_or_load_model('EN')
    speakers = model.hps.data.spk2id
    spk = speakers.get(MELOTTS_SPEAKER)
    if spk is None:
        spk = speakers.get('EN-IND') or list(speakers.values())[0]
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        model.tts_to_file('Hello.', spk, tmp_path, speed=MELOTTS_SPEED)
    finally:
        os.remove(tmp_path)
    logger.info('MeloTTS warmup complete speaker=%s', MELOTTS_SPEAKER)


class MeloTTSManager:
    """Wrapper for MeloTTS — one synthesis unit in, one PCM blob out."""

    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._active_voice: str | None = None
        self._lock = Lock()

        device = MELOTTS_DEVICE
        if device == 'auto':
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

        self.device = device
        self.speed = MELOTTS_SPEED
        self.default_speaker = MELOTTS_SPEAKER

    def _get_or_load_model(self, lang_code: str):
        with self._lock:
            if lang_code not in self._models:
                try:
                    from melo.api import TTS

                    logger.info(
                        'Loading MeloTTS model for language: %s on %s',
                        lang_code,
                        self.device,
                    )
                    self._models[lang_code] = TTS(language=lang_code, device=self.device)
                except ImportError:
                    logger.error(
                        'MeloTTS is not installed. '
                        'pip install melo @ git+https://github.com/myshell-ai/MeloTTS.git'
                    )
                    raise
            return self._models[lang_code]

    def set_active_voice(self, voice_id: str | None) -> None:
        self._active_voice = voice_id

    def synthesize_stream_sync(self, text: str, reply_script: str = 'en') -> Iterator[tuple[bytes, int]]:
        del reply_script
        cleaned = text.strip()
        if not cleaned:
            return

        lang_code = 'EN'

        try:
            model = self._get_or_load_model(lang_code)
            speaker_ids = model.hps.data.spk2id
            spk_id = speaker_ids.get(self.default_speaker)
            if spk_id is None:
                spk_id = speaker_ids.get('EN-IND')
            if spk_id is None:
                spk_id = list(speaker_ids.values())[0]

            pcm, sr = self._synthesize_sentence(model, spk_id, cleaned)
            if pcm:
                yield pcm, sr
        except Exception:
            logger.exception('MeloTTS synthesis failed')
            raise

    def _synthesize_sentence(self, model, spk_id: int, text: str) -> tuple[bytes, int]:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            model.tts_to_file(text, spk_id, tmp_path, speed=self.speed)
            data, samplerate = sf.read(tmp_path, dtype='int16')
            pcm_bytes = ensure_pcm_s16le_bytes(data.tobytes())
            return pcm_bytes, int(samplerate)
        finally:
            os.remove(tmp_path)

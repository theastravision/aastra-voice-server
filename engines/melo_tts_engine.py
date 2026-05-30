"""MeloTTS Engine integration for Hindi and Hinglish TTS."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from threading import Lock

import numpy as np
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


class MeloTTSManager:
    """Wrapper for MeloTTS."""

    def __init__(self) -> None:
        self._models: dict[str, any] = {}
        self._active_voice: str | None = None
        self._lock = Lock()
        
        # Determine device
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
                    logger.info("Loading MeloTTS model for language: %s on %s", lang_code, self.device)
                    self._models[lang_code] = TTS(language=lang_code, device=self.device)
                except ImportError:
                    logger.error("MeloTTS is not installed. Please install it using `pip install melo @ git+https://github.com/myshell-ai/MeloTTS.git`")
                    raise
            return self._models[lang_code]

    def set_active_voice(self, voice_id: str | None) -> None:
        self._active_voice = voice_id

    def synthesize_stream_sync(self, text: str, reply_script: str = 'en') -> Iterator[tuple[bytes, int]]:
        """
        Synthesizes text using MeloTTS and yields PCM s16le chunks.
        MeloTTS generates the whole audio very fast; we'll yield it as a single block.
        """
        cleaned = text.strip()
        if not cleaned:
            return

        lang_code = 'EN'
        if reply_script.lower() in ('hi', 'hinglish', 'devanagari'):
            # MeloTTS EN model handles mixed code-switching fairly well if trained,
            # or we use an explicit model if available. MeloTTS primary models are EN, ZH, FR, JP, KR, ES.
            # Using EN for Hinglish/Indian English if no explicit IN model.
            lang_code = 'EN'
            
        try:
            model = self._get_or_load_model(lang_code)
            speaker_ids = model.hps.data.spk2id
            
            # Use configured speaker, fallback to first available if not found
            spk_id = speaker_ids.get(self.default_speaker)
            if spk_id is None:
                spk_id = list(speaker_ids.values())[0]

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name

            # Generate audio to temporary file
            model.tts_to_file(cleaned, spk_id, tmp_path, speed=self.speed)
            
            # Read back using soundfile
            data, samplerate = sf.read(tmp_path, dtype='int16')
            os.remove(tmp_path)
            
            # Convert to bytes
            pcm_bytes = data.tobytes()
            yield pcm_bytes, samplerate
            
        except Exception as e:
            logger.exception("MeloTTS synthesis failed")
            raise

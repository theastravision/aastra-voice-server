"""faster-whisper STT with GPU support."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from config import (
    WHISPER_BEAM_SIZE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
    WHISPER_MODEL_PATH,
    effective_whisper_vad_filter,
)
from engines.audio_convert import bytes_to_wav_path
from engines.lang_detect import (
    resolve_whisper_language,
    whisper_initial_prompt,
)

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()

_VAD_PARAMS = {
    'min_silence_duration_ms': 500,
    'speech_pad_ms': 200,
}


def _ensure_ld_library_path() -> None:
    try:
        import nvidia.cublas.lib as cublas_lib
        import nvidia.cudnn.lib as cudnn_lib

        cublas_dir = os.path.dirname(cublas_lib.__file__)
        cudnn_dir = os.path.dirname(cudnn_lib.__file__)
        existing = os.environ.get('LD_LIBRARY_PATH', '')
        merged = f'{cublas_dir}:{cudnn_dir}'
        if merged not in existing:
            os.environ['LD_LIBRARY_PATH'] = f'{merged}:{existing}' if existing else merged
    except ImportError:
        pass


def get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            _ensure_ld_library_path()
            from faster_whisper import WhisperModel

            device = WHISPER_DEVICE
            if device == 'cuda':
                try:
                    import torch

                    if not torch.cuda.is_available():
                        logger.warning('CUDA unavailable; falling back to CPU for Whisper')
                        device = 'cpu'
                except ImportError:
                    device = 'cpu'
            compute = WHISPER_COMPUTE_TYPE if device == 'cuda' else 'int8'
            model_id = WHISPER_MODEL
            if WHISPER_MODEL_PATH and Path(WHISPER_MODEL_PATH).is_dir():
                model_id = WHISPER_MODEL_PATH
                logger.info('Using fine-tuned Whisper from %s', model_id)
            logger.info(
                'Loading Whisper model=%s device=%s compute=%s',
                model_id,
                device,
                compute,
            )
            _model = WhisperModel(model_id, device=device, compute_type=compute)
    return _model


def _suffix_for_filename(filename: str) -> str:
    name = (filename or 'audio.webm').lower()
    for ext in ('.webm', '.wav', '.mp3', '.ogg', '.m4a', '.flac'):
        if name.endswith(ext):
            return ext
    return '.webm'


def _build_transcribe_kwargs(
    lang: str | None,
    *,
    session_hint: str | None = None,
) -> dict:
    beam = WHISPER_BEAM_SIZE
    if lang == 'hi' or (session_hint or '').lower() in ('hi', 'hinglish'):
        beam = max(WHISPER_BEAM_SIZE, 5)
    kwargs: dict = {
        'beam_size': beam,
        'vad_filter': effective_whisper_vad_filter(),
        'condition_on_previous_text': False,
    }
    if effective_whisper_vad_filter():
        kwargs['vad_parameters'] = _VAD_PARAMS
    if lang:
        kwargs['language'] = lang
    prompt = whisper_initial_prompt(lang or session_hint)
    if prompt:
        kwargs['initial_prompt'] = prompt
    return kwargs


def transcribe_bytes(audio_bytes: bytes, *, filename: str = 'audio.webm', language: str | None = None) -> dict:
    if not audio_bytes:
        return {'text': '', 'detected_language': 'en'}

    suffix = _suffix_for_filename(filename)
    wav_path = bytes_to_wav_path(audio_bytes, suffix=suffix)
    model = get_model()
    lang = resolve_whisper_language(language)

    try:
        segments, info = model.transcribe(wav_path, **_build_transcribe_kwargs(lang, session_hint=language))
        text = ''.join(seg.text for seg in segments).strip()
        detected = getattr(info, 'language', None) or lang or 'en'
        return {'text': text, 'detected_language': detected}
    finally:
        Path(wav_path).unlink(missing_ok=True)


def warmup() -> None:
    try:
        get_model()
        logger.info('Whisper model loaded')
    except Exception:
        logger.exception('Whisper warmup failed (non-fatal)')

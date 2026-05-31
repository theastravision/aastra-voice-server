"""F5-TTS inference manager with hot VRAM voice cache and Vocos vocoder."""

from __future__ import annotations

from core.cuda_runtime import configure_cuda_runtime

configure_cuda_runtime()

import io
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import (
    ASTRA_DEFAULT_REF_TEXT,
    F5_CFG_STRENGTH,
    F5_CKPT_FILE,
    F5_CROSS_FADE_DURATION,
    F5_DEVANAGARI_NO_SPLIT_MAX_CHARS,
    F5_DTYPE,
    F5_HF_CACHE_DIR,
    F5_HINGLISH_SCRIPT,
    F5_HINGLISH_SPEED,
    F5_MODEL,
    F5_NFE_STEPS,
    F5_NO_SPLIT_MAX_CHARS,
    F5_SPEED,
    F5_SWAY_COEF,
    F5_VOCODER,
    resolve_f5_ref_paths,
    TTS_OUTPUT_FORMAT,
    is_legacy_f5_ref_text,
)
from engines.tts_text_pipeline import prepare_text_for_f5_tts, split_for_f5_chunks
from engines.tts_utils import ensure_pcm_s16le_bytes, wav_to_mp3
from engines.voice_registry import VoiceProfile, get_default_voice_id, get_voice

logger = logging.getLogger(__name__)

_manager: F5TTSInferenceManager | None = None
_manager_lock = threading.Lock()
_import_error: str | None = None


@dataclass
class _VoiceConditioning:
    ref_audio_path: str
    ref_text: str
    ref_audio_tensor: object
    ref_sr: int
    max_chars: int
    few_chars: int
    min_chars: int
    speed: float


def f5_available() -> bool:
    global _import_error
    if _import_error is not None:
        return False
    try:
        import f5_tts  # noqa: F401

        return True
    except ImportError as exc:
        _import_error = str(exc)
        return False


def _resolve_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return 'cuda'
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
    except ImportError:
        pass
    return 'cpu'


def _torch_dtype():
    import torch

    mapping = {
        'float16': torch.float16,
        'float32': torch.float32,
        'bfloat16': torch.bfloat16,
    }
    return mapping.get(F5_DTYPE.lower(), torch.float16)


def _resolve_ref_text(ref_text: str) -> str:
    if is_legacy_f5_ref_text(ref_text):
        logger.warning(
            'Legacy F5 ref_text detected; using ASTRA_DEFAULT_REF_TEXT. '
            'Run: python scripts/setup_ref_audio.py --force'
        )
        return ASTRA_DEFAULT_REF_TEXT
    return ref_text


def _fallback_ref_paths(
    *,
    voice_id: str | None = None,
    reply_script: str | None = None,
) -> tuple[str, str]:
    ref_audio, ref_text = resolve_f5_ref_paths(
        voice_id=voice_id,
        reply_script=reply_script,
    )
    path = Path(ref_audio)
    if not path.is_file():
        path = Path(ref_audio)
        if not path.is_absolute():
            from config import _ROOT

            path = _ROOT / path
    if path.is_file():
        return str(path.resolve()), _resolve_ref_text(ref_text)
    raise FileNotFoundError(
        f'F5 reference audio not found: {ref_audio}. '
        'Run: pip install edge-tts && python scripts/setup_ref_audio.py --force'
    )


def _profile_with_env_refs(
    profile: VoiceProfile | None,
    voice_id: str,
    *,
    reply_script: str | None = None,
) -> VoiceProfile:
    """Overlay language-specific env ref paths onto registry voice profile."""
    ref_audio, ref_text = resolve_f5_ref_paths(
        voice_id=voice_id,
        reply_script=reply_script,
        language=profile.language if profile else None,
    )
    if profile is None:
        return VoiceProfile(
            id=voice_id,
            display_name=voice_id,
            language='hinglish' if reply_script in ('hi', 'hinglish') else 'en-in',
            ref_audio=ref_audio,
            ref_text=_resolve_ref_text(ref_text),
            source='env',
        )
    return VoiceProfile(
        id=profile.id,
        display_name=profile.display_name,
        language=profile.language,
        ref_audio=ref_audio,
        ref_text=_resolve_ref_text(ref_text),
        source=profile.source,
        speed=profile.speed,
        created_at=profile.created_at,
    )


class F5TTSInferenceManager:
    """Loads F5-TTS + Vocos once; caches per-voice conditioning in VRAM."""

    def __init__(self) -> None:
        if not f5_available():
            raise RuntimeError(
                'f5-tts not installed. Run: bash scripts/install-f5-tts.sh'
            )
        from importlib.resources import files
        from cached_path import cached_path
        from f5_tts.infer.utils_infer import (
            chunk_text,
            infer_batch_process,
            load_model,
            load_vocoder,
            preprocess_ref_audio_text,
        )
        from hydra.utils import get_class
        from omegaconf import OmegaConf
        import torch

        self._chunk_text = chunk_text
        self._infer_batch_process = infer_batch_process
        self._preprocess_ref = preprocess_ref_audio_text
        self._device = _resolve_device()
        self._dtype = _torch_dtype() if self._device == 'cuda' else torch.float32

        model_cfg = OmegaConf.load(str(files('f5_tts').joinpath(f'configs/{F5_MODEL}.yaml')))
        model_cls = get_class(f'f5_tts.model.{model_cfg.model.backbone}')
        model_arc = model_cfg.model.arch
        self.mel_spec_type = F5_VOCODER or model_cfg.model.mel_spec.mel_spec_type
        self.sample_rate = model_cfg.model.mel_spec.target_sample_rate

        logger.info(
            'Loading F5-TTS model=%s vocoder=%s device=%s dtype=%s',
            F5_MODEL,
            self.mel_spec_type,
            self._device,
            self._dtype,
        )

        self.vocoder = load_vocoder(
            self.mel_spec_type,
            is_local=False,
            local_path=None,
            device=self._device,
            hf_cache_dir=F5_HF_CACHE_DIR,
        )

        ckpt_file = F5_CKPT_FILE
        if not ckpt_file:
            ckpt_file = str(
                cached_path(
                    f'hf://SWivid/F5-TTS/{F5_MODEL}/model_1250000.safetensors',
                    cache_dir=F5_HF_CACHE_DIR,
                )
            )

        self.model = load_model(
            model_cls,
            model_arc,
            ckpt_path=ckpt_file,
            mel_spec_type=self.mel_spec_type,
            vocab_file='',
            ode_method='euler',
            use_ema=True,
            device=self._device,
        )
        if self._device == 'cuda':
            self.model = self.model.to(self._device, dtype=self._dtype)

        self._voice_cache: dict[str, _VoiceConditioning] = {}
        self._active_voice_id = get_default_voice_id()
        self._active_reply_script: str | None = None
        self._first_package = True
        self._inference_lock = threading.Lock()
        self._cache_lock = threading.Lock()

        self.set_active_voice(self._active_voice_id)

    def _load_conditioning(self, profile: VoiceProfile) -> _VoiceConditioning:
        import torchaudio

        ref_path = str(profile.ref_audio_path())
        ref_path, ref_text = self._preprocess_ref(
            ref_path, profile.ref_text, show_info=logger.info
        )
        ref_audio_tensor, ref_sr = torchaudio.load(ref_path)
        ref_duration = ref_audio_tensor.shape[-1] / ref_sr
        ref_bytes = len(ref_text.encode('utf-8'))
        script = (self._active_reply_script or '').lower()
        if script in ('hi', 'hinglish'):
            speed = F5_HINGLISH_SPEED
        else:
            speed = profile.speed if profile.speed is not None else F5_SPEED
        max_chars = max(
            50,
            int(ref_bytes / max(ref_duration, 0.1) * (22 - ref_duration) * speed),
        )
        return _VoiceConditioning(
            ref_audio_path=ref_path,
            ref_text=ref_text,
            ref_audio_tensor=ref_audio_tensor,
            ref_sr=ref_sr,
            max_chars=max_chars,
            few_chars=max(20, max_chars // 2),
            min_chars=max(10, max_chars // 4),
            speed=speed,
        )

    def _get_conditioning(
        self,
        voice_id: str,
        *,
        reply_script: str | None = None,
    ) -> _VoiceConditioning:
        cache_key = f'{voice_id}:{reply_script or ""}'
        with self._cache_lock:
            if cache_key in self._voice_cache:
                return self._voice_cache[cache_key]
        registry_profile = get_voice(voice_id)
        profile = _profile_with_env_refs(
            registry_profile, voice_id, reply_script=reply_script
        )
        try:
            cond = self._load_conditioning(profile)
        except FileNotFoundError:
            ref_path, ref_text = _fallback_ref_paths(
                voice_id=voice_id, reply_script=reply_script
            )
            profile = VoiceProfile(
                id=voice_id,
                display_name=voice_id,
                language=profile.language,
                ref_audio=ref_path,
                ref_text=ref_text,
                source='fallback',
            )
            cond = self._load_conditioning(profile)
        with self._cache_lock:
            self._voice_cache[cache_key] = cond
        logger.info('F5 voice cache loaded voice_id=%s ref=%s', voice_id, cond.ref_audio_path)
        return cond

    def set_active_voice(
        self,
        voice_id: str | None,
        *,
        reply_script: str | None = None,
    ) -> None:
        vid = voice_id or get_default_voice_id()
        self._active_voice_id = vid
        self._active_reply_script = reply_script
        self._get_conditioning(vid, reply_script=reply_script)
        self._first_package = True

    def invalidate_voice(self, voice_id: str) -> None:
        with self._cache_lock:
            stale = [k for k in self._voice_cache if k.split(':', 1)[0] == voice_id]
            for key in stale:
                del self._voice_cache[key]

    def reset_stream_state(self) -> None:
        self._first_package = True

    def synthesize_stream_sync(
        self,
        text: str,
        *,
        reply_script: str | None = None,
    ) -> Iterator[tuple[bytes, int]]:
        script = reply_script if reply_script in ('en', 'hi', 'hinglish') else 'en'
        cleaned = prepare_text_for_f5_tts(text, reply_script=script)  # type: ignore[arg-type]
        if not cleaned:
            return

        cond = self._get_conditioning(
            self._active_voice_id,
            reply_script=reply_script or self._active_reply_script,
        )
        use_devanagari = (
            F5_HINGLISH_SCRIPT == 'devanagari' and script in ('hi', 'hinglish')
        ) or any('\u0900' <= ch <= '\u097f' for ch in cleaned)
        no_split_max = (
            F5_DEVANAGARI_NO_SPLIT_MAX_CHARS if use_devanagari else F5_NO_SPLIT_MAX_CHARS
        )

        sentence_parts = split_for_f5_chunks(cleaned) if use_devanagari else [cleaned]
        batches: list[str] = []
        for part in sentence_parts:
            batches.extend(self._chunk_text(part, max_chars=cond.max_chars))

        if (
            self._first_package
            and len(cleaned) > no_split_max
            and batches
            and len(batches[0]) > cond.few_chars
        ):
            first = batches[0]
            mini = self._chunk_text(first, max_chars=cond.few_chars)
            if mini and len(mini) > 1:
                batches = mini + batches[1:]
            self._first_package = False
        elif self._first_package:
            self._first_package = False

        stream = self._infer_batch_process(
            (cond.ref_audio_tensor, cond.ref_sr),
            cond.ref_text,
            batches,
            self.model,
            self.vocoder,
            progress=None,
            device=self._device,
            streaming=True,
            chunk_size=2048,
            nfe_step=F5_NFE_STEPS,
            sway_sampling_coef=F5_SWAY_COEF,
            cfg_strength=F5_CFG_STRENGTH,
            speed=cond.speed,
            cross_fade_duration=F5_CROSS_FADE_DURATION,
        )

        with self._inference_lock:
            for audio_chunk, _ in stream:
                if audio_chunk is None or len(audio_chunk) == 0:
                    continue
                pcm = ensure_pcm_s16le_bytes(np.asarray(audio_chunk, dtype=np.float32))
                if pcm:
                    yield pcm, self.sample_rate

    def synthesize_wav_bytes(
        self,
        text: str,
        *,
        reply_script: str | None = None,
    ) -> tuple[bytes, str]:
        chunks: list[bytes] = []
        sr = self.sample_rate
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

    def synthesize_mp3(self, text: str, *, voice: str = 'astra') -> tuple[bytes, str]:
        self.set_active_voice(voice)
        wav_bytes, _ = self.synthesize_wav_bytes(text)
        if not wav_bytes:
            return b'', 'audio/mpeg'
        return wav_to_mp3(wav_bytes), 'audio/mpeg'

    def warmup(self, voice_id: str | None = None) -> None:
        if voice_id:
            self.set_active_voice(voice_id)
        logger.info('F5-TTS warmup inference voice=%s', self._active_voice_id)
        for _pcm, _sr in self.synthesize_stream_sync('Warm up.'):
            break
        logger.info('F5-TTS warmup complete')


def get_manager() -> F5TTSInferenceManager:
    global _manager
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is None:
            _manager = F5TTSInferenceManager()
    return _manager


def invalidate_all_voice_cache() -> None:
    global _manager
    if _manager is None:
        return
    with _manager._cache_lock:
        _manager._voice_cache.clear()
    logger.info('F5 voice conditioning cache cleared')


def warmup() -> None:
    if not f5_available():
        raise RuntimeError('f5-tts not installed')
    from engines.voice_registry import migrate_registry_legacy_refs

    migrate_registry_legacy_refs()
    mgr = get_manager()
    mgr.warmup(get_default_voice_id())


def synthesize_audio(
    text: str,
    *,
    reply_script: str | None = None,
    voice: str = 'astra',
    lang: str | None = None,
) -> tuple[bytes, str]:
    mgr = get_manager()
    mgr.set_active_voice(voice)
    script = reply_script if reply_script in ('en', 'hi', 'hinglish') else 'en'
    return mgr.synthesize_wav_bytes(text, reply_script=script)


def synthesize_mp3(text: str, *, voice: str = 'astra') -> tuple[bytes, str]:
    return get_manager().synthesize_mp3(text, voice=voice)

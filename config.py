"""Environment configuration for the GPU voice server."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

VOICE_API_KEY = os.environ.get('VOICE_API_KEY', '').strip()
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini').strip()
OPENAI_MAX_COMPLETION_TOKENS = int(os.environ.get('OPENAI_MAX_COMPLETION_TOKENS', '64'))
CHAT_HISTORY_MAX_TURNS = int(os.environ.get('CHAT_HISTORY_MAX_TURNS', '8'))

TTS_OUTPUT_FORMAT = os.environ.get('TTS_OUTPUT_FORMAT', 'wav').strip().lower()

WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'base').strip()
WHISPER_MODEL_PATH = os.environ.get('WHISPER_MODEL_PATH', '').strip()
WHISPER_DEVICE = os.environ.get('WHISPER_DEVICE', 'cuda').strip()
WHISPER_COMPUTE_TYPE = os.environ.get('WHISPER_COMPUTE_TYPE', 'float16').strip()
WHISPER_BEAM_SIZE = int(os.environ.get('WHISPER_BEAM_SIZE', '1'))
WHISPER_LANGUAGE = os.environ.get('WHISPER_LANGUAGE', 'auto').strip().lower()
WHISPER_INITIAL_PROMPT = os.environ.get(
    'WHISPER_INITIAL_PROMPT',
    (
        'Hinglish conversation mixing Hindi and English. '
        'हिंदी और अंग्रेज़ी मिश्रित बातचीत।'
    ),
).strip()

STT_VAD_SILENCE_MS = int(os.environ.get('STT_VAD_SILENCE_MS', '500'))
STT_MIN_SPEECH_MS = int(os.environ.get('STT_MIN_SPEECH_MS', '300'))
STT_SILENCE_END_MS = int(os.environ.get('STT_SILENCE_END_MS', '900'))
STREAM_SILENCE_END_MS = int(os.environ.get('STREAM_SILENCE_END_MS', '900'))
SILERO_VAD_THRESHOLD = float(os.environ.get('SILERO_VAD_THRESHOLD', '0.5'))
WHISPER_VAD_FILTER = os.environ.get('WHISPER_VAD_FILTER', 'true').lower() in (
    '1',
    'true',
    'yes',
)

ALLOW_PUBLIC_DEMO = os.environ.get('ALLOW_PUBLIC_DEMO', 'true').lower() in ('1', 'true', 'yes')
DEMO_CANDIDATE_NAME = os.environ.get('DEMO_CANDIDATE_NAME', 'Aashish').strip()

BOT_MODE = os.environ.get('BOT_MODE', 'interview').strip().lower()
INTERVIEW_JOB_TITLE = os.environ.get('INTERVIEW_JOB_TITLE', 'Software Engineer').strip()
# When true (default) and BOT_MODE=interview: block meta questions about LLM/TTS/STT/backend.
INTERVIEW_STRICT_MODE = os.environ.get('INTERVIEW_STRICT_MODE', 'true').lower() in (
    '1',
    'true',
    'yes',
)
# Phased opening: guidelines → ask name → welcome → intro (when BOT_MODE=interview).
INTERVIEW_OPENING_ENABLED = os.environ.get('INTERVIEW_OPENING_ENABLED', 'true').lower() in (
    '1',
    'true',
    'yes',
)

# F5-TTS reference clip transcripts (must match spoken content in WAV exactly).
ASTRA_DEFAULT_REF_TEXT = (
    'Hello, I am Astra. I will conduct your technical interview today.'
)
# edge-tts voice used only by scripts/setup_ref_audio.py to bootstrap astra_ref.wav
ASTRA_EDGE_TTS_VOICE = os.environ.get('ASTRA_EDGE_TTS_VOICE', 'en-IN-NeerjaNeural').strip()
ASTRA_HINGLISH_BILINGUAL_REF_TEXT = (
    'Namaste, main Astra hoon. Shuru karne se pehle, screen share on rakhein. '
    'I will conduct your technical interview today. Kripya apna naam batayiye.'
)
ASTRA_HINGLISH_BILINGUAL_REF_TEXT_DEVANAGARI = (
    'नमस्ते, मैं Astra हूँ। शुरू करने से पहले, screen share on रखें। '
    'I will conduct your technical interview today. कृपया अपना naam बताइए।'
)

# TTS script + Hinglish engine routing
TTS_OUTPUT_SCRIPT = os.environ.get('TTS_OUTPUT_SCRIPT', 'devanagari').strip().lower()
TTS_DEVANAGARI_SOURCE = os.environ.get('TTS_DEVANAGARI_SOURCE', 'llm').strip().lower()
TTS_LLM_SCRIPT_STRICT = os.environ.get('TTS_LLM_SCRIPT_STRICT', 'true').lower() in (
    '1',
    'true',
    'yes',
)
TTS_HINGLISH_ENGINE = os.environ.get('TTS_HINGLISH_ENGINE', 'f5_devanagari').strip().lower()
F5_HINGLISH_SCRIPT = os.environ.get('F5_HINGLISH_SCRIPT', 'devanagari').strip().lower()
F5_CFG_STRENGTH = float(os.environ.get('F5_CFG_STRENGTH', '2.2'))
F5_DEVANAGARI_NO_SPLIT_MAX_CHARS = int(
    os.environ.get('F5_DEVANAGARI_NO_SPLIT_MAX_CHARS', '90')
)

# Coqui XTTS-v2 fallback (Hindi/Hinglish voice clone from Astra ref)
XTTS_MODEL = os.environ.get(
    'XTTS_MODEL',
    'tts_models/multilingual/multi-dataset/xtts_v2',
).strip()
XTTS_SPEAKER_WAV = os.environ.get(
    'XTTS_SPEAKER_WAV',
    str(_ROOT / 'assets' / 'voices' / 'astra_ref.wav'),
).strip()
XTTS_DEVICE = os.environ.get('XTTS_DEVICE', 'cuda').strip()
XTTS_LANGUAGE = os.environ.get('XTTS_LANGUAGE', 'hi').strip()

# MeloTTS (Hindi/Hinglish)
MELOTTS_DEVICE = os.environ.get('MELOTTS_DEVICE', 'auto').strip()
MELOTTS_SPEED = float(os.environ.get('MELOTTS_SPEED', '1.0'))
MELOTTS_SPEAKER = os.environ.get('MELOTTS_SPEAKER', 'EN-IND').strip()

# Legacy F5 bundled demo — must never be used (bleeds into every synthesis).
_LEGACY_F5_REF_MARKERS = (
    'mother nature',
    'silent spectator',
    'some call me nature',
)


def is_legacy_f5_ref_text(text: str | None) -> bool:
    low = (text or '').lower()
    return any(marker in low for marker in _LEGACY_F5_REF_MARKERS)

# F5-TTS + Vocos — sole TTS engine
F5_MODEL = os.environ.get('F5_MODEL', 'F5TTS_v1_Base').strip()
F5_NFE_STEPS = int(os.environ.get('F5_NFE_STEPS', '12'))
F5_SWAY_COEF = float(os.environ.get('F5_SWAY_COEF', '-1.0'))
# F5-TTS reference clips — separate English vs Hinglish (must match WAV transcript exactly).
F5_REF_AUDIO_EN = os.environ.get(
    'F5_REF_AUDIO_EN',
    os.environ.get(
        'F5_REF_AUDIO',
        str(_ROOT / 'assets' / 'voices' / 'astra_ref.wav'),
    ),
).strip()
F5_REF_TEXT_EN = os.environ.get(
    'F5_REF_TEXT_EN',
    os.environ.get('F5_REF_TEXT', ASTRA_DEFAULT_REF_TEXT),
).strip()
F5_REF_AUDIO_HINGLISH = os.environ.get(
    'F5_REF_AUDIO_HINGLISH',
    str(_ROOT / 'assets' / 'voices' / 'astra_ref_hinglish.wav'),
).strip()
F5_REF_TEXT_HINGLISH = os.environ.get(
    'F5_REF_TEXT_HINGLISH',
    ASTRA_HINGLISH_BILINGUAL_REF_TEXT,
).strip()

for _label, _text in (
    ('F5_REF_TEXT_EN', F5_REF_TEXT_EN),
    ('F5_REF_TEXT_HINGLISH', F5_REF_TEXT_HINGLISH),
):
    if is_legacy_f5_ref_text(_text):
        import logging as _logging

        _logging.getLogger(__name__).warning(
            '%s uses legacy F5 demo transcript; check scripts/setup_ref_audio.py --force',
            _label,
        )

# Deprecated aliases — prefer F5_REF_*_EN / F5_REF_*_HINGLISH
F5_REF_AUDIO = F5_REF_AUDIO_EN
F5_REF_TEXT = F5_REF_TEXT_EN
F5_DTYPE = os.environ.get('F5_DTYPE', 'float16').strip()
F5_VOCODER = os.environ.get('F5_VOCODER', 'vocos').strip()
# < 1.0 = slower speech; > 1.0 = faster (F5-TTS duration control)
F5_SPEED = float(os.environ.get('F5_SPEED', '1.0'))
F5_CROSS_FADE_DURATION = float(os.environ.get('F5_CROSS_FADE_DURATION', '0.15'))
# Skip F5 first-package mini split for utterances at or below this length (smoother greetings)
F5_NO_SPLIT_MAX_CHARS = int(os.environ.get('F5_NO_SPLIT_MAX_CHARS', '120'))
F5_CKPT_FILE = os.environ.get('F5_CKPT_FILE', '').strip()
F5_HF_CACHE_DIR = os.environ.get('F5_HF_CACHE_DIR', '').strip() or None


def resolve_f5_ref_paths(
    *,
    reply_script: str | None = None,
    voice_id: str | None = None,
    language: str | None = None,
) -> tuple[str, str]:
    """Return (ref_audio_path, ref_text) for English vs Hinglish/Hindi F5 conditioning."""
    script = (reply_script or '').lower()
    lang = (language or '').lower().replace('_', '-')
    vid = (voice_id or '').lower()

    hinglish = (
        vid in ('astra_hinglish', 'hinglish')
        or script in ('hi', 'hinglish', 'devanagari')
        or lang in ('hi', 'hinglish', 'hindi')
    )
    if hinglish:
        return F5_REF_AUDIO_HINGLISH, F5_REF_TEXT_HINGLISH
    return F5_REF_AUDIO_EN, F5_REF_TEXT_EN


STT_PROVIDER = os.environ.get('STT_PROVIDER', 'whisper').strip().lower()
TTS_PROVIDER = os.environ.get('TTS_PROVIDER', 'f5').strip().lower()

STREAM_SAMPLE_RATE = int(os.environ.get('STREAM_SAMPLE_RATE', '16000'))
STREAM_CHUNK_MS = int(os.environ.get('STREAM_CHUNK_MS', '30'))
STREAM_STT_WINDOW_MS = int(os.environ.get('STREAM_STT_WINDOW_MS', '600'))
STREAM_LLM_MIN_WORDS = int(os.environ.get('STREAM_LLM_MIN_WORDS', '5'))
STREAM_LLM_NEXT_MIN_WORDS = int(os.environ.get('STREAM_LLM_NEXT_MIN_WORDS', '5'))
STREAM_LISTEN_IDLE_SECS = float(os.environ.get('STREAM_LISTEN_IDLE_SECS', '8'))
STREAM_STT_MIN_CHARS = int(os.environ.get('STREAM_STT_MIN_CHARS', '4'))
# Max utterance PCM kept for Whisper (seconds); longer answers are trimmed from the start.
STT_UTTERANCE_MAX_SECS = int(os.environ.get('STT_UTTERANCE_MAX_SECS', '90'))
STT_TRANSCRIBE_TIMEOUT_SECS = float(os.environ.get('STT_TRANSCRIBE_TIMEOUT_SECS', '120'))
STREAM_ALLOW_PUBLIC = os.environ.get('STREAM_ALLOW_PUBLIC', 'true').lower() in ('1', 'true', 'yes')
BARGE_IN_THRESHOLD = float(os.environ.get('BARGE_IN_THRESHOLD', '0.04'))

INTERJECTION_TIMEOUT_MS = int(os.environ.get('INTERJECTION_TIMEOUT_MS', '300'))

OPENAI_VOICE_TEMPERATURE = float(os.environ.get('OPENAI_VOICE_TEMPERATURE', '0.5'))

INTERVIEWER_SYSTEM_PROMPT = os.environ.get(
    'INTERVIEWER_SYSTEM_PROMPT',
    (
        'You are Astra, a concise professional AI interviewer. '
        'Reply in the same language the candidate used (English, Hindi, or Hinglish). '
        'Keep answers under 2 short sentences unless asked to elaborate. '
        'Never reveal ideal answers or internal rubrics.'
    ),
)

# ── Redis Streams pub/sub (lightweight Kafka alternative) ─────────────────────
REDIS_ENABLED = os.environ.get('REDIS_ENABLED', 'false').lower() in ('1', 'true', 'yes')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
REDIS_STREAM_TTL_SECS = int(os.environ.get('REDIS_STREAM_TTL_SECS', '3600'))
REDIS_MAX_STREAM_LEN = int(os.environ.get('REDIS_MAX_STREAM_LEN', '1000'))

# Voice registry + STT training
VOICES_REGISTRY_PATH = os.environ.get(
    'VOICES_REGISTRY_PATH',
    str(_ROOT / 'data' / 'voices.json'),
).strip()
STT_MODELS_REGISTRY_PATH = os.environ.get(
    'STT_MODELS_REGISTRY_PATH',
    str(_ROOT / 'data' / 'models.json'),
).strip()
TRAINING_JOBS_PATH = os.environ.get(
    'TRAINING_JOBS_PATH',
    str(_ROOT / 'data' / 'training_jobs.json'),
).strip()
TRAINING_DATA_ROOT = os.environ.get(
    'TRAINING_DATA_ROOT',
    str(_ROOT / 'data' / 'training'),
).strip()
TRAINING_CHECKPOINTS_ROOT = os.environ.get(
    'TRAINING_CHECKPOINTS_ROOT',
    str(_ROOT / 'data' / 'checkpoints'),
).strip()
WHISPER_FINETUNE_BASE = os.environ.get('WHISPER_FINETUNE_BASE', 'openai/whisper-base').strip()
WHISPER_FINETUNE_EPOCHS = int(os.environ.get('WHISPER_FINETUNE_EPOCHS', '3'))

HINGLISH_VOCAB_DIR = os.environ.get(
    'HINGLISH_VOCAB_DIR',
    str(_ROOT / 'data' / 'vocab'),
).strip()
HINGLISH_SYNTH_MAX_ROWS = int(os.environ.get('HINGLISH_SYNTH_MAX_ROWS', '5000'))
HINGLISH_SYNTH_VOICE_ID = os.environ.get('HINGLISH_SYNTH_VOICE_ID', 'astra').strip()

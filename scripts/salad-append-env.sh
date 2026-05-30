#!/usr/bin/env bash
# Salad GPU: append recommended env vars to .env (safe to run more than once).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ENV_FILE"
    echo "Created .env from .env.example"
  else
    touch "$ENV_FILE"
    echo "Created empty .env"
  fi
fi

MARKER="# --- salad-append-env (do not duplicate) ---"
if grep -qF "$MARKER" "$ENV_FILE" 2>/dev/null; then
  echo ".env already has Salad block ($MARKER). Edit .env manually or remove that line and re-run."
  exit 0
fi

cat >>"$ENV_FILE" <<'EOF'

# --- salad-append-env (do not duplicate) ---
HOST=*
PORT=8000
ALLOW_PUBLIC_DEMO=true
BOT_MODE=interview
INTERVIEW_STRICT_MODE=true
INTERVIEW_OPENING_ENABLED=true
INTERVIEW_JOB_TITLE=Software Engineer
DEMO_CANDIDATE_NAME=Aashish

OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_COMPLETION_TOKENS=64
OPENAI_VOICE_TEMPERATURE=0.5
CHAT_HISTORY_MAX_TURNS=8

STT_PROVIDER=whisper_chunk
TTS_PROVIDER=f5
F5_MODEL=F5TTS_v1_Base
F5_NFE_STEPS=18
F5_SWAY_COEF=-1.0
F5_SPEED=0.85
F5_CROSS_FADE_DURATION=0.15
F5_REF_AUDIO=assets/voices/astra_ref.wav
F5_DTYPE=float16
F5_VOCODER=vocos
STREAM_LLM_MIN_WORDS=3
STREAM_LLM_NEXT_MIN_WORDS=5
INTERJECTION_TIMEOUT_MS=300
STREAM_LISTEN_IDLE_SECS=8
STREAM_STT_MIN_CHARS=12
TTS_OUTPUT_FORMAT=wav

WHISPER_MODEL=base
WHISPER_LANGUAGE=auto
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WHISPER_BEAM_SIZE=1
STT_VAD_SILENCE_MS=600
STT_MIN_SPEECH_MS=300
WHISPER_VAD_FILTER=false
WHISPER_INITIAL_PROMPT=Hinglish conversation mixing Hindi and English. हिंदी और अंग्रेज़ी मिश्रित बातचीत।

STREAM_ALLOW_PUBLIC=true
STREAM_SAMPLE_RATE=16000
STREAM_CHUNK_MS=30
STREAM_STT_WINDOW_MS=600

# ngrok (scripts/run-all.sh reads this)
NGROK_AUTHTOKEN=
EOF

echo "Appended Salad env block to $ENV_FILE"
echo "Set secrets (if not already set):"
echo "  OPENAI_API_KEY=sk-..."
echo "  F5_REF_TEXT=Hello, I am Astra. I will conduct your technical interview today."
echo "  (Regenerate ref WAV: pip install edge-tts && python scripts/setup_ref_audio.py --force)"

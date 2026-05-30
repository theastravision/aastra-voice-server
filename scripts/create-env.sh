#!/usr/bin/env bash
# Create .env without vi/nano (minimal containers).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
  echo ".env already exists: $ENV_FILE"
  echo "Delete first to recreate: rm .env"
  exit 0
fi

OPENAI_API_KEY="${OPENAI_API_KEY:-}"
HF_TOKEN="${HF_TOKEN:-}"
VOICE_API_KEY="${VOICE_API_KEY:-}"

if [[ -z "$OPENAI_API_KEY" ]]; then
  printf 'OPENAI_API_KEY (sk-...): '
  read -r OPENAI_API_KEY
fi
if [[ -z "$HF_TOKEN" ]]; then
  printf 'HF_TOKEN (optional, for HuggingFace downloads): '
  read -r HF_TOKEN
fi
if [[ -z "$VOICE_API_KEY" ]]; then
  printf 'VOICE_API_KEY (optional, leave empty for demo): '
  read -r VOICE_API_KEY
fi

cat > "$ENV_FILE" << EOF
VOICE_API_KEY=${VOICE_API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY}
HF_TOKEN=${HF_TOKEN}
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_COMPLETION_TOKENS=128
CHAT_HISTORY_MAX_TURNS=8

BOT_MODE=interview
STT_PROVIDER=whisper_chunk
TTS_PROVIDER=f5
F5_MODEL=F5TTS_v1_Base
F5_NFE_STEPS=18
F5_REF_AUDIO=assets/voices/astra_ref.wav

WHISPER_MODEL=base
WHISPER_LANGUAGE=auto
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WHISPER_BEAM_SIZE=1
TTS_OUTPUT_FORMAT=wav

STREAM_ALLOW_PUBLIC=true
ALLOW_PUBLIC_DEMO=true
DEMO_CANDIDATE_NAME=Aashish
HOST=*
PORT=8000
EOF

chmod 600 "$ENV_FILE" 2>/dev/null || true
echo "Created $ENV_FILE"

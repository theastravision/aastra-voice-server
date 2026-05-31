#!/usr/bin/env bash
# Start Kenpath svara-TTS API in .venv-svara (default port 8080).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv-svara"
VENDOR="$ROOT/vendor/svara-tts-inference"
PID_FILE="$ROOT/svara-sidecar.pid"
LOG="$ROOT/svara-sidecar.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env"

SVARA_TTS_URL="${SVARA_TTS_URL:-http://127.0.0.1:8080}"
SVARA_PORT="${SVARA_PORT:-8080}"
if [[ "$SVARA_TTS_URL" =~ :([0-9]+)(/|$) ]]; then
  SVARA_PORT="${BASH_REMATCH[1]}"
fi

BACKGROUND=0
for arg in "$@"; do
  if [[ "$arg" == "--background" || "$arg" == "-b" ]]; then
    BACKGROUND=1
  fi
done

if [[ ! -d "$VENV" ]]; then
  echo "Missing .venv-svara — run: bash scripts/install-svara-tts.sh"
  exit 1
fi
if [[ ! -d "$VENDOR/api" ]]; then
  echo "Missing vendor/svara-tts-inference — run: bash scripts/install-svara-tts.sh"
  exit 1
fi

_health_ok() {
  curl -sf --max-time 3 "${SVARA_TTS_URL%/}/health" >/dev/null 2>&1
}

if _health_ok; then
  echo "svara sidecar already healthy on http://${SVARA_TTS_URL#*://}"
  exit 0
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "svara pid ${OLD_PID} warming or unhealthy — check: tail -f $LOG"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ":${SVARA_PORT} "; then
  echo "Port ${SVARA_PORT} already in use — stop existing service or change SVARA_TTS_URL"
  ss -tlnp 2>/dev/null | grep ":${SVARA_PORT} " || true
  exit 1
fi

export VLLM_MODEL="${SVARA_MODEL:-kenpath/svara-tts-v1}"
export VLLM_GPU_MEMORY_UTILIZATION="${SVARA_VLLM_GPU_MEMORY_UTILIZATION:-0.50}"
export VLLM_MAX_MODEL_LEN="${SVARA_VLLM_MAX_MODEL_LEN:-4096}"
export SNAC_DEVICE="${SVARA_SNAC_DEVICE:-cuda}"
export API_HOST="${SVARA_API_HOST:-127.0.0.1}"
export API_PORT="${SVARA_PORT}"
export LOG_LEVEL="${SVARA_LOG_LEVEL:-INFO}"

if [[ "$BACKGROUND" -eq 1 ]]; then
  rm -f "$PID_FILE"
  (
    cd "$VENDOR/api"
    exec "$VENV/bin/python" server.py
  ) >> "$LOG" 2>&1 &
  SIDECAR_PID=$!
  echo "$SIDECAR_PID" > "$PID_FILE"
  echo "Started svara sidecar pid ${SIDECAR_PID} on http://${API_HOST}:${SVARA_PORT}"
  echo "Log: $LOG"
else
  echo "Starting svara sidecar on http://${API_HOST}:${SVARA_PORT} (foreground)"
  cd "$VENDOR/api"
  exec "$VENV/bin/python" server.py
fi

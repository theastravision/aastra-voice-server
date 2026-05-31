#!/usr/bin/env bash
# Start voice server (foreground). For background: bash scripts/run-demo-background.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run: bash scripts/install-demo.sh first"
  exit 1
fi

# POSIX sh (Salad default) has no "source" — use "." 
. .venv/bin/activate

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env"

export LD_LIBRARY_PATH="$(python -c 'from core.cuda_runtime import cuda_library_path_export; print(cuda_library_path_export())')"

# Salad Container Gateway needs dual-stack bind (see docs.salad.com quickstart)
HOST="${HOST:-*}"
PORT="${PORT:-8000}"

TTS_INDIC_ENGINE="${TTS_INDIC_ENGINE:-svara}"
if [[ "$TTS_INDIC_ENGINE" == "svara" ]]; then
  echo "Starting svara sidecar in background (Indic TTS — loads in .venv-svara)..."
  if ! bash "$ROOT/scripts/run-svara-sidecar.sh" --background; then
    echo "WARN: svara sidecar did not start — Indic TTS may fall back to F5"
    echo "      Fix: bash scripts/install-svara-tts.sh && tail -f svara-sidecar.log"
  else
    sleep 2
    SIDECAR_PID_FILE="$ROOT/svara-sidecar.pid"
    if [[ -f "$SIDECAR_PID_FILE" ]] && kill -0 "$(cat "$SIDECAR_PID_FILE")" 2>/dev/null; then
      echo "  svara pid $(cat "$SIDECAR_PID_FILE") warming on :8080 — may take several minutes on first load"
      echo "  tail -f $ROOT/svara-sidecar.log"
      echo "  when ready: curl ${SVARA_TTS_URL:-http://127.0.0.1:8080}/health"
    else
      echo "ERROR: svara sidecar exited immediately — Indic TTS will use F5 until fixed"
      tail -25 "$ROOT/svara-sidecar.log" 2>/dev/null || echo "  (no svara-sidecar.log)"
      echo "  Fix: bash scripts/install-svara-tts.sh && bash scripts/run-svara-sidecar.sh --background"
    fi
  fi
fi

UVICORN_HOST="$HOST"
if [[ "$UVICORN_HOST" == "*" ]]; then
  UVICORN_HOST="0.0.0.0"
fi

echo "Starting voice server on http://${UVICORN_HOST}:${PORT}"
echo "  Health:  http://127.0.0.1:${PORT}/health"
echo "  Docs:    http://127.0.0.1:${PORT}/docs"
echo "  Talk:    POST /api/v1/voice-turn (multipart audio)"
exec python -m uvicorn main:app --host "$UVICORN_HOST" --port "$PORT"

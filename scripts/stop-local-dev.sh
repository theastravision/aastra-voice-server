#!/usr/bin/env bash
# Stop run-local-dev.sh processes (uvicorn + Vite).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VOICE_PID_FILE="$ROOT/.local-dev-voice.pid"
UI_PORT="${UI_PORT:-5173}"

if [[ -f "$VOICE_PID_FILE" ]]; then
  pid="$(cat "$VOICE_PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 0.5
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$VOICE_PID_FILE"
fi

bash "$ROOT/scripts/stop-voice.sh" 2>/dev/null || true

pkill -f 'vite.*interview-ui' 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  fuser -k "${UI_PORT}/tcp" 2>/dev/null || true
fi

echo "Stopped local dev (voice server + interview-ui)."

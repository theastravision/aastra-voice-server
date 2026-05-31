#!/usr/bin/env bash
# Stop svara-TTS sidecar and free its port.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PID_FILE="$ROOT/svara-sidecar.pid"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env" 2>/dev/null || true

SVARA_TTS_URL="${SVARA_TTS_URL:-http://127.0.0.1:8080}"
SVARA_PORT="${SVARA_PORT:-8080}"
if [[ "$SVARA_TTS_URL" =~ :([0-9]+)(/|$) ]]; then
  SVARA_PORT="${BASH_REMATCH[1]}"
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

pkill -f 'vendor/svara-tts-inference/api/server.py' 2>/dev/null || true
pkill -f 'svara-tts-inference/api/server.py' 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  fuser -k "${SVARA_PORT}/tcp" 2>/dev/null || true
elif command -v ss >/dev/null 2>&1; then
  PIDS=$(ss -tlnp 2>/dev/null | grep ":${SVARA_PORT} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)
  for p in $PIDS; do
    kill "$p" 2>/dev/null || true
    sleep 0.5
    kill -9 "$p" 2>/dev/null || true
  done
fi

sleep 1
if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ":${SVARA_PORT} "; then
  echo "WARNING: port ${SVARA_PORT} may still be in use"
else
  echo "Stopped svara sidecar; port ${SVARA_PORT} is free"
fi

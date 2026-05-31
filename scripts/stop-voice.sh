#!/usr/bin/env bash
# Stop voice server and free PORT (default 9001).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PID_FILE="$ROOT/voice-server.pid"
NGROK_PID_FILE="$ROOT/ngrok.pid"
PORT="${PORT:-8000}"

bash "$ROOT/scripts/stop-svara-sidecar.sh" 2>/dev/null || true

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

pkill -f 'uvicorn main:app' 2>/dev/null || true
pkill -f 'python -m uvicorn main:app' 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
elif command -v ss >/dev/null 2>&1; then
  PIDS=$(ss -tlnp 2>/dev/null | grep ":${PORT} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)
  for p in $PIDS; do
    kill "$p" 2>/dev/null || true
    sleep 0.5
    kill -9 "$p" 2>/dev/null || true
  done
fi

if [[ -f "$NGROK_PID_FILE" ]]; then
  NGROK_PID="$(cat "$NGROK_PID_FILE")"
  if kill -0 "$NGROK_PID" 2>/dev/null; then
    kill "$NGROK_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$NGROK_PID" 2>/dev/null || true
  fi
  rm -f "$NGROK_PID_FILE"
fi
pkill -f 'ngrok http' 2>/dev/null || true

sleep 1
if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
  echo "WARNING: port ${PORT} may still be in use. Check: ss -tlnp | grep ${PORT}"
else
  echo "Stopped voice server; port ${PORT} is free"
fi

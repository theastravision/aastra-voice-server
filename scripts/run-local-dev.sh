#!/usr/bin/env bash
# Start voice server (uvicorn :8000) + React interview UI (Vite :5173).
# Stop with Ctrl+C or: bash scripts/stop-local-dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
VOICE_PID_FILE="$ROOT/.local-dev-voice.pid"

if [[ ! -d .venv ]]; then
  echo "Run first: bash scripts/install-demo.sh"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required for the React UI. Install Node.js 20+ and retry."
  exit 1
fi

# shellcheck disable=SC1091
. .venv/bin/activate
# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env"

export LD_LIBRARY_PATH="$(python -c 'import os
try:
    import nvidia.cublas.lib as c
    import nvidia.cudnn.lib as d
    print(os.path.dirname(c.__file__) + ":" + os.path.dirname(d.__file__))
except ImportError:
    print(os.environ.get("LD_LIBRARY_PATH", ""))')"

if [[ -f "$VOICE_PID_FILE" ]] && kill -0 "$(cat "$VOICE_PID_FILE")" 2>/dev/null; then
  echo "Voice server already running (pid $(cat "$VOICE_PID_FILE")). Run: bash scripts/stop-local-dev.sh"
  exit 1
fi

UI_DIR="$ROOT/interview-ui"
if [[ ! -d "$UI_DIR" ]]; then
  echo "Missing $UI_DIR"
  exit 1
fi

if [[ ! -d "$UI_DIR/node_modules" ]]; then
  echo "Installing interview-ui dependencies..."
  (cd "$UI_DIR" && npm install)
fi

cleanup() {
  if [[ -f "$VOICE_PID_FILE" ]]; then
    pid="$(cat "$VOICE_PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.5
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$VOICE_PID_FILE"
  fi
  pkill -f "python -m uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "=============================================="
echo "  Bot (recommended)  http://127.0.0.1:${PORT}/bot"
echo "  React UI            http://127.0.0.1:${UI_PORT}"
echo "  Health              http://127.0.0.1:${PORT}/health"
echo "=============================================="
echo "Starting voice server: uvicorn main:app --host ${HOST} --port ${PORT}"
echo "Then starting Vite (proxies /ws and /api to :${PORT})"
echo "Press Ctrl+C to stop both."
echo ""

python -m uvicorn main:app --host "$HOST" --port "$PORT" &
echo $! >"$VOICE_PID_FILE"

sleep 2

cd "$UI_DIR"
exec npm run dev -- --host 127.0.0.1 --port "$UI_PORT"

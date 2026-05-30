#!/usr/bin/env bash
# Keep server running after you close SSH.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/voice-server.log"
PID="$ROOT/voice-server.pid"
export HOST="${HOST:-*}"
export PORT="${PORT:-8000}"

if [[ -f "$PID" ]] && kill -0 "$(cat "$PID")" 2>/dev/null; then
  echo "Already running (pid $(cat "$PID")). Stop with: bash scripts/stop-voice.sh"
  exit 0
fi

if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
  echo "Port ${PORT} is in use. Run: bash scripts/stop-voice.sh"
  ss -tlnp 2>/dev/null | grep ":${PORT} " || true
  exit 1
fi

rm -f "$PID"
nohup bash scripts/run-demo.sh >> "$LOG" 2>&1 &
echo $! > "$PID"
echo "Started pid $(cat "$PID") on port ${PORT}. Log: $LOG"
echo "Wait ~60s for model warmup, then: curl http://127.0.0.1:${PORT}/health"
echo "Tail log: tail -f $LOG"

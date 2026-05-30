#!/usr/bin/env bash
# Stop Jupyter on PORT, start voice server with Salad-compatible bind (HOST=*).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-9001}"

echo "Stopping Jupyter on port ${PORT} (if any)..."
pkill -f 'jupyter-lab' 2>/dev/null || true
pkill -f 'jupyter lab' 2>/dev/null || true
pkill -f jupyter 2>/dev/null || true
sleep 2

if [[ -f voice-server.pid ]] && kill -0 "$(cat voice-server.pid)" 2>/dev/null; then
  kill "$(cat voice-server.pid)" 2>/dev/null || true
  sleep 1
fi

export HOST='*'
export PORT
echo "Starting voice server on HOST=* PORT=${PORT}..."
bash scripts/run-demo-background.sh
sleep 5

echo ""
bash scripts/diagnose-salad.sh

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
  echo "Starting svara sidecar (Indic TTS)..."
  bash "$ROOT/scripts/run-svara-sidecar.sh" --background
  bash "$ROOT/scripts/wait-svara-health.sh"
fi

echo "Starting voice server on http://${HOST}:${PORT}"
echo "  Health:  http://127.0.0.1:${PORT}/health"
echo "  Docs:    http://127.0.0.1:${PORT}/docs"
echo "  Talk:    POST /api/v1/voice-turn (multipart audio)"
exec python -m uvicorn main:app --host "$HOST" --port "$PORT"

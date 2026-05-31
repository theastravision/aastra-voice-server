#!/usr/bin/env bash
# Print the port where the voice server is (or should be) reachable on localhost.
# Prefers PORT from env; auto-detects Salad :8888 when nothing on PORT.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env" 2>/dev/null || true

PORT="${PORT:-8000}"
SALAD_PORT="${SALAD_PORT:-8888}"

health_ok() {
  curl -sf --max-time 2 "http://127.0.0.1:$1/health" >/dev/null 2>&1
}

if health_ok "$PORT"; then
  echo "$PORT"
  exit 0
fi

if [[ "$PORT" != "$SALAD_PORT" ]] && health_ok "$SALAD_PORT"; then
  echo "Note: voice server on :${SALAD_PORT} (Salad) — add PORT=${SALAD_PORT} to .env" >&2
  echo "$SALAD_PORT"
  exit 0
fi

# Nothing listening — return configured PORT (caller may wait for startup)
echo "$PORT"

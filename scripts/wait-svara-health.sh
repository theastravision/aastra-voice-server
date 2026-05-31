#!/usr/bin/env bash
# Wait until svara sidecar responds to GET /health.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env" 2>/dev/null || true

SVARA_TTS_URL="${SVARA_TTS_URL:-http://127.0.0.1:8080}"
HEALTH_URL="${SVARA_TTS_URL%/}/health"
MAX_WAIT="${SVARA_HEALTH_WAIT_SEC:-300}"
INTERVAL="${SVARA_HEALTH_POLL_SEC:-2}"

echo "Waiting for svara sidecar at ${HEALTH_URL} (max ${MAX_WAIT}s)..."

deadline=$((SECONDS + MAX_WAIT))
while (( SECONDS < deadline )); do
  if curl -sf --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "svara sidecar healthy"
    exit 0
  fi
  sleep "$INTERVAL"
done

echo "ERROR: svara sidecar did not become healthy within ${MAX_WAIT}s" >&2
echo "Check: tail -f $ROOT/svara-sidecar.log" >&2
exit 1

#!/usr/bin/env bash
# Verify voice server + ngrok port alignment.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env"

PORT="${PORT:-8000}"
echo "==> Checking voice server port (configured PORT=${PORT})"
RESOLVED="$(bash "$ROOT/scripts/resolve-service-port.sh" 2>/dev/null | tail -1)"
echo "==> Resolved localhost port: ${RESOLVED}"
PORT="$RESOLVED"
if command -v ss >/dev/null 2>&1; then
  ss -tlnp 2>/dev/null | grep ":${PORT} " || echo "Nothing listening on ${PORT}"
else
  netstat -tlnp 2>/dev/null | grep ":${PORT} " || echo "Nothing listening on ${PORT}"
fi

echo "==> Health (must return JSON immediately)"
if curl -sf "http://127.0.0.1:${PORT}/health"; then
  echo ""
else
  echo "FAIL: curl http://127.0.0.1:${PORT}/health"
  echo "Start server: PORT=${PORT} HOST='*' bash scripts/run-demo-background.sh"
  exit 1
fi

echo ""
echo "==> models_ready should become true after warmup (~60s). Re-run:"
echo "  curl -s http://127.0.0.1:${PORT}/health | python3 -m json.tool"
echo ""
echo "==> ngrok must tunnel to the same port (IPv4 localhost):"
echo "  ngrok http http://127.0.0.1:${PORT}"

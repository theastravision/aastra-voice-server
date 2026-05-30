#!/usr/bin/env bash
# Verify voice server + ngrok port alignment.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env"

PORT="${PORT:-8000}"
echo "==> Checking port ${PORT}"
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
echo "==> ngrok must use the SAME port:"
echo "  ngrok http ${PORT}"

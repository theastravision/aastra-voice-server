#!/usr/bin/env bash
# Quick check: are voice server / svara / ngrok running?
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env" 2>/dev/null || true

PORT="${PORT:-8000}"
SVARA_URL="${SVARA_TTS_URL:-http://127.0.0.1:8080}"

echo "========== Processes =========="
ps aux 2>/dev/null | grep -E 'uvicorn main:app|run-demo|svara.*server\.py|ngrok http' | grep -v grep || echo "(none found)"

echo ""
echo "========== Listening ports =========="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp 2>/dev/null | grep -E ':8000 |:8080 |:8888 |:4040 ' || echo "(no 8000/8080/8888/4040 listeners)"
else
  netstat -tlnp 2>/dev/null | grep -E ':8000 |:8080 |:8888 ' || true
fi

echo ""
echo "========== Health checks =========="
for url in \
  "http://127.0.0.1:${PORT}/health" \
  "http://127.0.0.1:8888/health" \
  "http://127.0.0.1:8000/health" \
  "${SVARA_URL%/}/health"; do
  if curl -sf --max-time 3 "$url" >/dev/null 2>&1; then
    echo "OK   $url"
  else
    echo "FAIL $url"
  fi
done

echo ""
echo "========== PID files =========="
for f in voice-server.pid svara-sidecar.pid ngrok.pid; do
  if [[ -f "$ROOT/$f" ]]; then
    pid="$(cat "$ROOT/$f")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "alive $f pid=$pid"
    else
      echo "dead $f pid=$pid (stale)"
    fi
  else
    echo "missing $f"
  fi
done

echo ""
echo "========== Last log lines =========="
echo "--- voice-server.log ---"
tail -15 "$ROOT/voice-server.log" 2>/dev/null || echo "(no log)"
echo "--- svara-sidecar.log ---"
tail -15 "$ROOT/svara-sidecar.log" 2>/dev/null || echo "(no log)"

echo ""
echo "========== Fix =========="
echo "  bash scripts/run-all.sh"
echo "  tail -f voice-server.log"
echo "  PORT in .env: $(grep '^PORT=' .env 2>/dev/null || echo 'not set')"

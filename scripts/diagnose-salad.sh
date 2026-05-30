#!/usr/bin/env bash
# Run inside Salad container to fix gateway /health issues.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-9001}"

echo "========== 1. What is listening on port $PORT? =========="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp | grep ":$PORT " || echo "(nothing on $PORT)"
else
  netstat -tlnp 2>/dev/null | grep ":$PORT " || echo "(cannot list ports — install ss or netstat)"
fi

echo ""
echo "========== 2. Local voice health (must succeed) =========="
if curl -sf "http://127.0.0.1:${PORT}/health" 2>/dev/null; then
  echo ""
  echo "OK: voice server responds locally"
else
  echo "FAIL: no voice server on 127.0.0.1:${PORT}"
  echo "Fix: HOST='*' PORT=${PORT} bash scripts/run-demo-background.sh"
  echo "     tail -20 voice-server.log"
fi

echo ""
echo "========== 3. Jupyter on $PORT? (blocks voice + /health) =========="
if pgrep -af jupyter 2>/dev/null | head -3; then
  echo "Jupyter is running — stop it if gateway port is ${PORT}:"
  echo "  pkill -f jupyter-lab || pkill -f jupyter"
fi

echo ""
echo "========== 4. Voice server process =========="
if [[ -f voice-server.pid ]] && kill -0 "$(cat voice-server.pid)" 2>/dev/null; then
  echo "voice-server pid $(cat voice-server.pid) running"
else
  echo "voice-server not running (no pid file or dead)"
fi

echo ""
echo "========== 5. .env =========="
grep -E '^(PORT|HOST|VOICE_API_KEY|OPENAI)' .env 2>/dev/null | sed 's/OPENAI_API_KEY=.*/OPENAI_API_KEY=***/' || echo "no .env"

echo ""
echo "========== Salad portal checklist =========="
echo "  - Container Gateway port = ${PORT}"
echo "  - Gateway auth ON  -> curl needs: Salad-Api-Key header"
echo "  - Gateway auth OFF -> curl without Salad-Api-Key"
echo "  - Only ONE app on ${PORT} (voice server, not Jupyter)"
echo "  - Public URL: https://YOUR-GROUP.salad.cloud/health"

#!/usr/bin/env bash
# One script for Salad: stop → (optional install) → start → wait for health.
# Uses F5-TTS + Vocos (bash scripts/install-f5-tts.sh).
#
# Prefer the all-in-one script (install + build + ngrok):
#   bash scripts/run-all.sh
#
# Usage:
#   bash scripts/salad-run.sh              # stop + start
#   bash scripts/salad-run.sh --install    # first time: venv + deps + models
#   bash scripts/salad-run.sh --ngrok      # stop + start + ngrok http $PORT
#   bash scripts/salad-run.sh --build-ui   # npm run build → /interview (React)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/voice-server.log"
PID_FILE="$ROOT/voice-server.pid"

DO_INSTALL=false
DO_NGROK=false
DO_BUILD_UI=false
for arg in "$@"; do
  case "$arg" in
    --install|-i) DO_INSTALL=true ;;
    --ngrok|-n) DO_NGROK=true ;;
    --build-ui|-u) DO_BUILD_UI=true ;;
    --help|-h)
      sed -n '2,13p' "$0"
      exit 0
      ;;
  esac
done

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env" 2>/dev/null || true

export HOST="${HOST:-*}"
export PORT="${PORT:-8000}"
export BOT_MODE="${BOT_MODE:-interview}"

if command -v sudo >/dev/null 2>&1; then
  APT="sudo apt-get"
elif [[ "$(id -u)" -eq 0 ]]; then
  APT="apt-get"
else
  APT=""
fi

ensure_env() {
  if [[ -f "$ROOT/.env" ]]; then
    return
  fi
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "Created .env from .env.example — set OPENAI_API_KEY inside .env"
  else
    echo "Missing .env — create one with OPENAI_API_KEY=sk-..."
    exit 1
  fi
  load_env_file "$ROOT/.env"
}

patch_env_tts() {
  ensure_env
  bash "$ROOT/scripts/salad-append-env.sh" 2>/dev/null || true
  load_env_file "$ROOT/.env"
  local tmp="$ROOT/.env.salad-run.tmp"
  grep -v '^TTS_PROVIDER=' "$ROOT/.env" \
    | grep -v '^BOT_MODE=' >"$tmp" || true
  if ! .venv/bin/python -c "from engines.f5_tts_engine import f5_available; exit(0 if f5_available() else 1)" 2>/dev/null; then
    echo "ERROR: f5-tts not installed. Run: bash scripts/salad-run.sh --install"
    exit 1
  fi
  {
    cat "$tmp"
    echo 'TTS_PROVIDER=f5'
    echo 'BOT_MODE=interview'
  } >"$ROOT/.env"
  rm -f "$tmp"
  load_env_file "$ROOT/.env"
  export TTS_PROVIDER=f5
}

stop_server() {
  echo "==> Stopping voice server (port ${PORT})"
  PORT="$PORT" bash "$ROOT/scripts/stop-voice.sh" || true
  pkill -f 'ngrok http' 2>/dev/null || true
}

setup_venv() {
  local PY=python3
  command -v "$PY" >/dev/null || { echo "python3 not found"; exit 1; }
  if [[ ! -d "$ROOT/.venv" ]]; then
    echo "==> Creating venv ($("$PY" --version))"
    "$PY" -m venv "$ROOT/.venv"
  fi
  # shellcheck disable=SC1091
  . "$ROOT/.venv/bin/activate"
  pip install --upgrade pip wheel setuptools
}

install_all() {
  echo "==> Salad install (Whisper + F5-TTS)"

  if [[ -n "$APT" ]]; then
    echo "==> System packages"
    $APT update
    $APT install -y \
      python3 python3-venv python3-pip \
      nodejs npm \
      espeak-ng ffmpeg libsndfile1 git curl wget \
      build-essential \
      || true
  fi

  setup_venv

  echo "==> PyTorch (CUDA 12.4)"
  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

  echo "==> Python dependencies"
  pip install -r "$ROOT/requirements.txt"
  pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"

  if ! bash "$ROOT/scripts/install-f5-tts.sh"; then
    echo "F5-TTS install failed"
    exit 1
  fi
  patch_env_tts

  export LD_LIBRARY_PATH="$(python -c 'from core.cuda_runtime import cuda_library_path_export; print(cuda_library_path_export())')"

  echo "==> Download / warm models"
  bash "$ROOT/scripts/download-models.sh"

  echo "==> React interview UI (for /interview)"
  bash "$ROOT/scripts/build-interview-ui.sh"

  echo "Install done."
}

start_server() {
  patch_env_tts
  if [[ ! -d "$ROOT/.venv" ]]; then
    echo "No .venv — run: bash scripts/salad-run.sh --install"
    exit 1
  fi

  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running pid $(cat "$PID_FILE")"
    return 0
  fi

  if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
    echo "Port ${PORT} in use — stopping first"
    stop_server
  fi

  echo "==> Starting voice server on port ${PORT}"
  export HOST PORT TTS_PROVIDER
  rm -f "$PID_FILE"
  nohup bash "$ROOT/scripts/run-demo.sh" >>"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
  echo "PID $(cat "$PID_FILE") — log: $LOG"
}

wait_for_health() {
  local max="${WAIT_HEALTH_SECS:-180}"
  local url="http://127.0.0.1:${PORT}/health"
  echo "==> Waiting for ${url} (up to ${max}s)"
  for ((i = 1; i <= max; i++)); do
    resp="$(curl -sf "$url" 2>/dev/null)" || { sleep 1; continue; }
    if echo "$resp" | grep -q '"models_ready":\s*true'; then
      echo "$resp"
      echo "==> Ready"
      return 0
    fi
    if (( i == 1 || i % 15 == 0 )); then
      echo "  … warming models (${i}s)"
    fi
    sleep 1
  done
  echo "WARNING: models not ready after ${max}s — check: tail -50 $LOG"
  curl -sf "$url" 2>/dev/null || true
  return 1
}

start_ngrok() {
  if ! command -v ngrok >/dev/null 2>&1; then
    echo "ngrok not installed — run in another terminal: ngrok http ${PORT}"
    return 1
  fi
  load_env_file "$ROOT/.env"
  if [[ -n "${NGROK_AUTHTOKEN:-}" ]]; then
    ngrok config add-authtoken "$NGROK_AUTHTOKEN" 2>/dev/null || true
  fi
  echo "==> Starting ngrok (Salad / voice server port)"
  local ngrok_port upstream
  ngrok_port="$(bash "$ROOT/scripts/resolve-service-port.sh" 2>/dev/null | tail -1)"
  upstream="http://127.0.0.1:${ngrok_port}"
  echo "==> ngrok → ${upstream}"
  nohup ngrok http "$upstream" --log=stdout >>"$ROOT/ngrok.log" 2>&1 &
  echo $! >"$ROOT/ngrok.pid"
  sleep 2
  if curl -sf http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -o 'https://[^"]*ngrok[^"]*' | head -1; then
    curl -sf http://127.0.0.1:4040/api/tunnels | python3 -c "
import json,sys
d=json.load(sys.stdin)
for t in d.get('tunnels',[]):
    u=t.get('public_url','')
    if u.startswith('https:'):
        print('Public URL:', u)
        print('Bot UI:     ', u + '/bot')
" 2>/dev/null || true
  else
    echo "ngrok started — open http://127.0.0.1:4040 or: tail -f $ROOT/ngrok.log"
  fi
}

# --- main ---
stop_server

if $DO_INSTALL; then
  install_all
elif $DO_BUILD_UI; then
  bash "$ROOT/scripts/build-interview-ui.sh"
fi

start_server
wait_for_health || true

if $DO_NGROK; then
  start_ngrok || true
fi

echo ""
echo "Done (Salad / remote GPU — no local PC required)."
echo "  Health (in container): http://127.0.0.1:${PORT}/health"
echo "  Bot (HTML):          http://127.0.0.1:${PORT}/bot"
if [[ -f "$ROOT/interview-ui/dist/index.html" ]]; then
  echo "  Interview (React):   http://127.0.0.1:${PORT}/interview"
else
  echo "  Interview (React):   not built — run: bash scripts/build-interview-ui.sh"
fi
echo "  Public URL: Salad Container Gateway or ngrok → https://YOUR-HOST/interview"
echo "  Logs:         tail -f $LOG"
echo "  Stop:         bash scripts/stop-voice.sh"
if ! $DO_NGROK; then
  echo "  Tunnel:       bash scripts/salad-run.sh --ngrok"
fi

#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Aastra Voice Server — ONE script: install (if needed) → build UI → run → ngrok
#
# Usage (Salad / Linux GPU):
#   cd /workspace/voice-server
#   chmod +x scripts/run-all.sh
#
#   # Put secrets in .env first (OPENAI_API_KEY, optional NGROK_AUTHTOKEN), then:
#   bash scripts/run-all.sh
#
#   # Or pass ngrok token once (also saved to .env if missing):
#   NGROK_AUTHTOKEN=your_token bash scripts/run-all.sh
#   bash scripts/run-all.sh --ngrok-token your_token
#
#   # Force full reinstall:
#   bash scripts/run-all.sh --install
#
#   # Skip ngrok tunnel:
#   bash scripts/run-all.sh --no-ngrok
#
# What it does every run:
#   1. Ensure .env exists
#   2. Install deps ONLY if .venv / F5-TTS missing (unless --install)
#   3. Build React UI (/interview)
#   4. Warm/download models (quick skip if already cached)
#   5. Stop old server + ngrok
#   6. Start voice server on PORT (default 8000)
#   7. Wait for /health models_ready
#   8. ngrok config add-authtoken + ngrok http 8000
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG="$ROOT/voice-server.log"
PID_FILE="$ROOT/voice-server.pid"
NGROK_LOG="$ROOT/ngrok.log"
NGROK_PID_FILE="$ROOT/ngrok.pid"

DO_INSTALL=false
DO_NGROK=true
NGROK_TOKEN_ARG=""

for arg in "$@"; do
  case "$arg" in
    --install|-i) DO_INSTALL=true ;;
    --no-ngrok) DO_NGROK=false ;;
    --ngrok-token=*) NGROK_TOKEN_ARG="${arg#*=}" ;;
    --ngrok-token)
      echo "Use: --ngrok-token=YOUR_TOKEN"
      exit 1
      ;;
    --help|-h)
      sed -n '3,32p' "$0"
      exit 0
      ;;
  esac
done

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env" 2>/dev/null || true

export HOST="${HOST:-*}"
export PORT="${PORT:-8000}"
export STT_VAD_SILENCE_MS="800"
export WHISPER_VAD_FILTER="true"

step() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  STEP $1 — $2"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

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
    echo "Created .env from .env.example"
    echo "  → Edit .env and set OPENAI_API_KEY (required)"
  else
    echo "ERROR: No .env or .env.example found"
    exit 1
  fi
}

ensure_ngrok_token_in_env() {
  local token="${NGROK_TOKEN_ARG:-${NGROK_AUTHTOKEN:-}}"
  if [[ -z "$token" ]] && [[ -f "$ROOT/.env" ]]; then
    token="$(grep -E '^NGROK_AUTHTOKEN=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'" || true)"
  fi
  if [[ -z "$token" ]]; then
    echo "WARN: No NGROK_AUTHTOKEN — set in .env or: NGROK_AUTHTOKEN=xxx bash scripts/run-all.sh"
    return 1
  fi
  export NGROK_AUTHTOKEN="$token"
  if [[ -f "$ROOT/.env" ]] && ! grep -qE '^NGROK_AUTHTOKEN=' "$ROOT/.env" 2>/dev/null; then
    echo "NGROK_AUTHTOKEN=$token" >>"$ROOT/.env"
    echo "Appended NGROK_AUTHTOKEN to .env"
  fi
  ngrok config add-authtoken "$token" 2>/dev/null || true
  return 0
}

ensure_ngrok_binary() {
  if command -v ngrok >/dev/null 2>&1; then
    return 0
  fi
  echo "Installing ngrok CLI…"
  local arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64)
      curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-amd64.tgz \
        | tar xz -C /usr/local/bin ngrok 2>/dev/null || \
      curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-amd64.tgz \
        | tar xz -C "$ROOT/bin" ngrok
      ;;
    aarch64|arm64)
      curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-arm64.tgz \
        | tar xz -C /usr/local/bin ngrok 2>/dev/null || \
      curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-arm64.tgz \
        | tar xz -C "$ROOT/bin" ngrok
      ;;
    *)
      echo "WARN: Unknown arch $arch — install ngrok manually"
      return 1
      ;;
  esac
  export PATH="/usr/local/bin:$ROOT/bin:$PATH"
  command -v ngrok >/dev/null 2>&1
}

needs_install() {
  if $DO_INSTALL; then
    return 0
  fi
  if [[ ! -d "$ROOT/.venv" ]]; then
    return 0
  fi
  if ! "$ROOT/.venv/bin/python" -c "from engines.f5_tts_engine import f5_available; exit(0 if f5_available() else 1)" 2>/dev/null; then
    return 0
  fi
  return 1
}

setup_venv() {
  local PY=python3
  command -v "$PY" >/dev/null || { echo "ERROR: python3 not found"; exit 1; }
  if [[ ! -d "$ROOT/.venv" ]]; then
    echo "Creating Python venv…"
    "$PY" -m venv "$ROOT/.venv"
  fi
  # shellcheck disable=SC1091
  . "$ROOT/.venv/bin/activate"
  pip install -q --upgrade pip wheel setuptools
}

install_all() {
  if [[ -n "$APT" ]]; then
    echo "Installing system packages (ffmpeg, nodejs, …)…"
    $APT update -qq
    $APT install -y -qq \
      python3 python3-venv python3-pip \
      nodejs npm \
      espeak-ng ffmpeg libsndfile1 git curl wget \
      build-essential \
      2>/dev/null || true
  fi

  setup_venv

  echo "Installing PyTorch (CUDA 12.4)…"
  pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu124

  echo "Installing Python requirements…"
  pip install -q -r "$ROOT/requirements.txt"
  pip install -q nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" 2>/dev/null || true

  echo "Installing F5-TTS…"
  bash "$ROOT/scripts/install-f5-tts.sh"

  bash "$ROOT/scripts/salad-append-env.sh" 2>/dev/null || true
  load_env_file "$ROOT/.env"

  echo "First-time install complete."
}

patch_env_tts() {
  ensure_env
  load_env_file "$ROOT/.env"
  bash "$ROOT/scripts/salad-append-env.sh" 2>/dev/null || true
  load_env_file "$ROOT/.env"
  if [[ ! -d "$ROOT/.venv" ]]; then
    echo "ERROR: No .venv — run: bash scripts/run-all.sh --install"
    exit 1
  fi
  if ! "$ROOT/.venv/bin/python" -c "from engines.f5_tts_engine import f5_available; exit(0 if f5_available() else 1)" 2>/dev/null; then
    echo "ERROR: f5-tts not installed — run: bash scripts/run-all.sh --install"
    exit 1
  fi
  ensure_astra_reference
  export TTS_PROVIDER=f5
  export BOT_MODE=interview
}

ensure_astra_reference() {
  local legacy=0
  local force=""
  if grep -qiE 'mother nature|silent spectator|some call me nature' "$ROOT/data/voices.json" 2>/dev/null; then
    legacy=1
  fi
  if [[ "$legacy" -eq 1 ]]; then
    force="--force"
  fi
  echo "Ensuring reference WAVs from data/voices.json…"
  pip install -q edge-tts 2>/dev/null || true
  "$ROOT/.venv/bin/python" "$ROOT/scripts/setup_ref_audio.py" $force || true
}

stop_all() {
  echo "Stopping voice server and ngrok…"
  PORT="$PORT" bash "$ROOT/scripts/stop-voice.sh" || true
  pkill -f 'ngrok http' 2>/dev/null || true
}

start_server() {
  patch_env_tts
  # shellcheck disable=SC1091
  . "$ROOT/.venv/bin/activate"
  load_env_file "$ROOT/.env"

  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running pid $(cat "$PID_FILE")"
    return 0
  fi

  echo "Starting voice server on http://${HOST}:${PORT}…"
  export HOST PORT TTS_PROVIDER
  rm -f "$PID_FILE"
  nohup bash "$ROOT/scripts/run-demo.sh" >>"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
  echo "PID $(cat "$PID_FILE") — log: $LOG"
}

wait_for_health() {
  local max="${WAIT_HEALTH_SECS:-180}"
  local url="http://127.0.0.1:${PORT}/health"
  echo "Waiting for models (up to ${max}s): $url"
  for ((i = 1; i <= max; i++)); do
    resp="$(curl -sf "$url" 2>/dev/null)" || { sleep 1; continue; }
    if echo "$resp" | grep -q '"models_ready":\s*true'; then
      echo "$resp" | python3 -m json.tool 2>/dev/null || echo "$resp"
      echo "Models ready."
      return 0
    fi
    if (( i == 1 || i % 15 == 0 )); then
      echo "  … warming (${i}s) — tail -f $LOG"
    fi
    sleep 1
  done
  echo "WARN: models not ready after ${max}s"
  tail -20 "$LOG" 2>/dev/null || true
  return 1
}

start_ngrok() {
  ensure_ngrok_binary || return 1
  ensure_ngrok_token_in_env || return 1

  echo "Starting ngrok http ${PORT}…"
  nohup ngrok http "$PORT" --log=stdout >>"$NGROK_LOG" 2>&1 &
  echo $! >"$NGROK_PID_FILE"
  sleep 3

  local public_url=""
  if curl -sf http://127.0.0.1:4040/api/tunnels 2>/dev/null; then
    public_url="$(curl -sf http://127.0.0.1:4040/api/tunnels | python3 -c "
import json, sys
d = json.load(sys.stdin)
for t in d.get('tunnels', []):
    u = t.get('public_url', '')
    if u.startswith('https:'):
        print(u)
        break
" 2>/dev/null || true)"
  fi

  if [[ -n "$public_url" ]]; then
    echo ""
    echo "  Public URL:    $public_url"
    echo "  Interview UI:  $public_url/interview/"
    echo "  Bot demo:      $public_url/bot"
    echo "  WebSocket:     wss://${public_url#https://}/ws/voice"
  else
    echo "ngrok running — dashboard: http://127.0.0.1:4040"
    echo "Log: tail -f $NGROK_LOG"
  fi
}

print_summary() {
  echo ""
  echo "══════════════════════════════════════════════════════════════════════════"
  echo "  DONE — Aastra Voice Server"
  echo "══════════════════════════════════════════════════════════════════════════"
  echo "  Local health:   http://127.0.0.1:${PORT}/health"
  echo "  Interview UI:   http://127.0.0.1:${PORT}/interview/"
  echo "  Training tab:   http://127.0.0.1:${PORT}/interview/  → Training"
  echo "  Bot demo:       http://127.0.0.1:${PORT}/bot"
  echo "  Server log:     tail -f $LOG"
  echo "  Stop all:       bash scripts/stop-voice.sh"
  echo "══════════════════════════════════════════════════════════════════════════"
}

# ─── MAIN ────────────────────────────────────────────────────────────────────

step 1 "Environment"
ensure_env
load_env_file "$ROOT/.env"
bash "$ROOT/scripts/salad-append-env.sh" 2>/dev/null || true
load_env_file "$ROOT/.env"
chmod +x "$ROOT/scripts/"*.sh 2>/dev/null || true

step 2 "Install (skip if already done)"
if needs_install; then
  install_all
else
  echo "Already installed (.venv + F5-TTS OK) — skipping full install."
  echo "  (Use --install to force reinstall)"
fi

step 3 "Build React UI"
bash "$ROOT/scripts/build-interview-ui.sh"

step 4 "Download / warm models"
if [[ -d "$ROOT/.venv" ]]; then
  bash "$ROOT/scripts/download-models.sh" || echo "WARN: model warmup had issues — server may still start"
else
  echo "SKIP: no .venv"
fi

step 5 "Stop previous server + ngrok"
stop_all

step 6 "Start voice server"
start_server

step 7 "Wait for health"
wait_for_health || true

step 8 "ngrok tunnel"
if $DO_NGROK; then
  start_ngrok || echo "WARN: ngrok not started — use Salad Container Gateway or fix NGROK_AUTHTOKEN"
else
  echo "Skipped (--no-ngrok)"
fi

print_summary

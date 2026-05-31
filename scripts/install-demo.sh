#!/usr/bin/env bash
# Manual demo install — Ubuntu / Salad terminal (often no sudo — run as root).
# Usage: cd ~/aastra-voice && bash scripts/install-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if command -v sudo >/dev/null 2>&1; then
  APT="sudo apt-get"
elif [[ "$(id -u)" -eq 0 ]]; then
  APT="apt-get"
else
  echo "No sudo and not root — install system packages yourself, then re-run:"
  echo "  apt-get install -y python3 python3-venv python3-pip espeak-ng ffmpeg libsndfile1 git curl wget"
  APT=""
fi

if [[ -n "$APT" ]]; then
  echo "==> System packages"
  $APT update
  $APT install -y \
    python3 python3-venv python3-pip \
    espeak-ng ffmpeg libsndfile1 git curl wget \
    build-essential \
    || true
fi

PY=python3
command -v "$PY" >/dev/null || { echo "python3 not found"; exit 1; }
echo "==> Using $PY ($($PY --version))"

echo "==> Python virtualenv"
$PY -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip wheel setuptools

echo "==> PyTorch (CUDA 12.4)"
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

echo "==> Voice server dependencies"
pip install -r requirements.txt
pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"

echo "==> F5-TTS + Vocos"
if ! bash scripts/install-f5-tts.sh; then
  echo ""
  echo "ERROR: F5-TTS install failed."
  exit 1
fi

echo "==> .env file"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ""
  echo "EDIT .env — set OPENAI_API_KEY, HF_TOKEN, and VOICE_API_KEY:"
  echo "  nano $ROOT/.env"
fi

echo "==> Pre-download models (Whisper + Parler warmup)"
export LD_LIBRARY_PATH="$(python -c 'from core.cuda_runtime import cuda_library_path_export; print(cuda_library_path_export())')"
bash scripts/download-models.sh

echo ""
echo "Install complete. Next:"
echo "  1. nano $ROOT/.env   # OPENAI_API_KEY + HF_TOKEN"
echo "  2. bash scripts/run-demo.sh"

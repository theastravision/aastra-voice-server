#!/usr/bin/env bash
# Install embedded svara-TTS (Kenpath) for Indic language synthesis.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/vendor/svara-tts-inference"
REPO="${SVARA_TTS_REPO:-https://github.com/Kenpath/svara-tts-inference.git}"

echo "==> svara-TTS vendor directory: $VENDOR"

if [[ ! -d "$VENDOR/.git" ]]; then
  mkdir -p "$ROOT/vendor"
  git clone --depth 1 "$REPO" "$VENDOR"
else
  echo "==> Updating svara-tts-inference..."
  git -C "$VENDOR" pull --ff-only || true
fi

echo "==> Installing svara Python dependencies..."
pip install -r "$ROOT/requirements-svara.txt"
if [[ -f "$VENDOR/requirements.txt" ]]; then
  pip install -r "$VENDOR/requirements.txt"
fi

echo "==> Done. Set in .env:"
echo "    TTS_INDIC_ENGINE=svara"
echo "    SVARA_VLLM_GPU_MEMORY_UTILIZATION=0.50"
echo "Restart the voice server after download completes on first warmup."

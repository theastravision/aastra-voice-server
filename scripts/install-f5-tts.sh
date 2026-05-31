#!/usr/bin/env bash
# Install F5-TTS + Vocos and copy default reference voice clip.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "No .venv — create one first: python3 -m venv .venv && source .venv/bin/activate"
  exit 1
fi

# shellcheck disable=SC1091
. "$ROOT/.venv/bin/activate"

echo "==> Installing F5-TTS + dependencies"
pip install --upgrade pip wheel setuptools
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124 || \
  pip install torch torchaudio
pip install -r "$ROOT/requirements.txt"
pip install nvidia-cuda-nvrtc-cu12 nvidia-cuda-runtime-cu12

echo "==> Setting up Astra reference voice clip (not F5 mother-nature demo)"
pip install edge-tts
if [[ -f "$ROOT/assets/voices/astra_ref.wav" ]]; then
  python "$ROOT/scripts/setup_ref_audio.py" || python "$ROOT/scripts/setup_ref_audio.py" --force
else
  python "$ROOT/scripts/setup_ref_audio.py"
fi

echo "==> Verifying F5-TTS import"
python - <<'PY'
from engines.f5_tts_engine import f5_available
if not f5_available():
    raise SystemExit("FAIL: f5-tts import failed")
print("OK: f5-tts importable")
PY

echo "Done. Set TTS_PROVIDER=f5 in .env and restart the server."

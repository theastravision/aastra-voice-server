#!/usr/bin/env bash
# Install Coqui XTTS-v2 for Hindi/Hinglish voice-clone fallback.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Create venv first: python -m venv .venv && source .venv/bin/activate"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install -U "coqui-tts>=0.24.0"

python - <<'PY'
from engines.xtts_engine import xtts_available
print('xtts_available:', xtts_available())
PY

echo "XTTS install complete. Set TTS_HINGLISH_ENGINE=xtts in .env to enable fallback."

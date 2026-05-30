#!/usr/bin/env bash
# Download / warm up Whisper + F5-TTS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
. .venv/bin/activate

# shellcheck disable=SC1091
source "$ROOT/scripts/load-env.sh"
load_env_file "$ROOT/.env"

export LD_LIBRARY_PATH="$(python -c 'import os
try:
    import nvidia.cublas.lib as c
    import nvidia.cudnn.lib as d
    print(os.path.dirname(c.__file__) + ":" + os.path.dirname(d.__file__))
except ImportError:
    print(os.environ.get("LD_LIBRARY_PATH", ""))')"

WHISPER_MODEL="${WHISPER_MODEL:-base}"
WHISPER_DEVICE="${WHISPER_DEVICE:-cuda}"

echo "==> Downloading Whisper: $WHISPER_MODEL"
python - << PY
from faster_whisper import WhisperModel
import os
model = os.environ.get("WHISPER_MODEL", "base")
device = os.environ.get("WHISPER_DEVICE", "cuda")
compute = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
try:
    import torch
    if device == "cuda" and not torch.cuda.is_available():
        print("CUDA not available — using CPU + int8")
        device, compute = "cpu", "int8"
except ImportError:
    pass
print(f"Loading {model} on {device} ({compute})...")
WhisperModel(model, device=device, compute_type=compute)
print("Whisper ready.")
PY

python "$ROOT/scripts/setup_ref_audio.py"

TTS_PROVIDER="${TTS_PROVIDER:-f5}"
python - << 'PY'
import os
import sys

sys.path.insert(0, ".")
provider = os.environ.get("TTS_PROVIDER", "f5").lower()
if provider != "f5":
    print(f"WARNING: only f5 TTS is supported; got {provider!r}")
from engines.f5_tts_engine import f5_available, warmup

if not f5_available():
    print("FAIL: f5-tts not installed. Run: bash scripts/install-f5-tts.sh")
    sys.exit(1)
print("==> Warming F5-TTS + Vocos")
warmup()
from engines.interjections import warmup_interjections
warmup_interjections()
print("F5-TTS ready.")
PY

echo "Models cached under ~/.cache/huggingface."

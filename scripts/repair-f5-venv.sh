#!/usr/bin/env bash
# Remove svara/vLLM from main .venv and restore F5-compatible torch (cu124 + NVRTC).
# svara belongs in .venv-svara only — never mix with F5.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
CHECK_ONLY=false
FORCE=false

for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=true ;;
    --force) FORCE=true ;;
  esac
done

if [[ ! -d "$VENV" ]]; then
  if $CHECK_ONLY; then
    exit 1
  fi
  echo "repair-f5-venv: no .venv — skip"
  exit 0
fi

# shellcheck disable=SC1091
. "$VENV/bin/activate"

needs_repair() {
  if $FORCE; then
    return 0
  fi
  if python -c "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('vllm') else 1)" 2>/dev/null; then
    return 0
  fi
  if python -c "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('flashinfer') else 1)" 2>/dev/null; then
    return 0
  fi
  if ! f5_cuda_ok; then
    return 0
  fi
  return 1
}

f5_cuda_ok() {
  python - <<'PY' 2>/dev/null
from core.cuda_runtime import configure_cuda_runtime
configure_cuda_runtime()
import torch
if not torch.cuda.is_available():
    raise SystemExit(1)
from torchaudio.transforms import MelSpectrogram
x = torch.randn(1, 16000, device="cuda")
mel = MelSpectrogram(sample_rate=24000, n_fft=1024, hop_length=256, n_mels=100).cuda()
mel(x)
PY
}

if $CHECK_ONLY; then
  if needs_repair; then
    exit 1
  fi
  exit 0
fi

if ! needs_repair; then
  echo "Main .venv F5/CUDA OK — no repair needed"
  exit 0
fi

echo "==> Repairing main .venv for F5 (remove svara contamination, restore cu124 torch)…"

if python -c "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('vllm') else 1)" 2>/dev/null; then
  echo "  Removing vLLM/svara packages from main .venv (use .venv-svara instead)…"
  pip uninstall -y vllm flashinfer-python snac torchcodec xformers 2>/dev/null || true
fi

echo "  Reinstalling PyTorch cu124 + CUDA helper wheels…"
pip install -q --upgrade pip wheel setuptools
pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -q nvidia-cuda-nvrtc-cu12 nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" 2>/dev/null || true

echo "  Verifying F5 CUDA mel spectrogram…"
if f5_cuda_ok; then
  echo "  OK: F5 CUDA mel spectrogram"
else
  echo "  WARN: F5 CUDA check still failing — run: bash scripts/install-f5-tts.sh"
  exit 1
fi

echo "==> Main .venv repair complete"

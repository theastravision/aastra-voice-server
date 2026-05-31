#!/usr/bin/env bash
# Install svara-TTS sidecar in a separate venv (.venv-svara) — never mix with F5 .venv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/vendor/svara-tts-inference"
VENV="$ROOT/.venv-svara"
REPO="${SVARA_TTS_REPO:-https://github.com/Kenpath/svara-tts-inference.git}"

echo "==> svara-TTS vendor directory: $VENDOR"

if [[ ! -d "$VENDOR/.git" ]]; then
  mkdir -p "$ROOT/vendor"
  git clone --depth 1 "$REPO" "$VENDOR"
else
  echo "==> Updating svara-tts-inference..."
  git -C "$VENDOR" pull --ff-only || true
fi

if [[ ! -d "$VENV" ]]; then
  echo "==> Creating svara sidecar venv: $VENV"
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
. "$VENV/bin/activate"

echo "==> Installing svara Python dependencies into .venv-svara (not main .venv)..."
pip install --upgrade pip wheel setuptools
pip install -r "$ROOT/requirements-svara-sidecar.txt"
if [[ -f "$VENDOR/requirements.txt" ]]; then
  pip install -r "$VENDOR/requirements.txt"
fi

echo "==> Verifying svara sidecar imports..."
python - <<'PY'
import vllm  # noqa: F401
print("OK: vllm importable in .venv-svara")
PY

echo "==> Done. Set in .env:"
echo "    TTS_INDIC_ENGINE=svara"
echo "    SVARA_TTS_URL=http://127.0.0.1:8080"
echo "    SVARA_VLLM_GPU_MEMORY_UTILIZATION=0.50"
echo ""
echo "Start sidecar: bash scripts/run-svara-sidecar.sh"
echo "Or start both: bash scripts/run-demo-background.sh"

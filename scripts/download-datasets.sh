#!/usr/bin/env bash
# Guide / optional small downloads for OSS training data (not bundled in repo).
# Usage:
#   bash scripts/download-datasets.sh --list
#   bash scripts/download-datasets.sh --sample-hi
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/datasets/oss_manifest.json"
DATA_ROOT="${DATASETS_DIR:-$ROOT/data/datasets}"

list_catalog() {
  python3 - << PY
import json
from pathlib import Path
m = json.loads(Path("$MANIFEST").read_text(encoding="utf-8"))
print(m["description"])
print()
print("=== STT datasets ===")
for d in m["stt_datasets"]:
    print(f"  [{d['id']}] {d['name']}")
    print(f"    ~hours: {d.get('hours_approx')}, samples: {d.get('samples_approx')}")
    print(f"    {d['url']}")
print()
print("=== TTS datasets ===")
for d in m["tts_datasets"]:
    print(f"  [{d['id']}] {d['name']}")
    print(f"    ~hours: {d.get('hours_approx')}, samples: {d.get('samples_approx')}")
    print(f"    {d['url']}")
print()
print("Notes:", m["combined_scale_notes"])
PY
}

sample_hi() {
  echo "==> Installing huggingface_hub if needed..."
  . "$ROOT/.venv/bin/activate" 2>/dev/null || true
  pip install -q huggingface_hub 2>/dev/null || pip install huggingface_hub
  mkdir -p "$DATA_ROOT/common_voice_hi"
  echo "==> Downloading small Hindi validation slice from Common Voice (config: hi, split: validated[:1%])"
  echo "    Target: $DATA_ROOT/common_voice_hi"
  python3 - << PY
from huggingface_hub import snapshot_download
import os
target = os.environ.get("DATA_ROOT", "$DATA_ROOT")
path = snapshot_download(
    repo_id="mozilla-foundation/common_voice_17_0",
    repo_type="dataset",
    allow_patterns=["hi/*"],
    local_dir=target + "/common_voice_17_hi",
    max_workers=4,
)
print("Downloaded to:", path)
print("Use this for fine-tuning experiments — not loaded automatically at runtime.")
PY
}

case "${1:-}" in
  --list) list_catalog ;;
  --sample-hi) export DATA_ROOT; sample_hi ;;
  *)
    echo "Usage: $0 --list | --sample-hi"
    echo "See docs/DATASETS_AND_TRAINING.md for full 10M–100M scale preparation."
    exit 1
    ;;
esac

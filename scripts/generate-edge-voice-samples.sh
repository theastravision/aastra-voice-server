#!/usr/bin/env bash
# Generate Edge TTS mp3 for each Microsoft neural voice (one by one, for testing).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

SAMPLE_TEXT="${SAMPLE_TEXT:-Hello Aashish, welcome to your technical interview.}"

echo "Generating Edge TTS voice samples one by one"
echo "Sample text: $SAMPLE_TEXT"
echo "Output: data/voice-samples/*.mp3 and data/edge_voices.json"
python scripts/generate_edge_voice_samples.py --text "$SAMPLE_TEXT" "$@"

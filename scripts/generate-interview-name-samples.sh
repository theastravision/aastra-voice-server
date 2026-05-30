#!/usr/bin/env bash
# Generate Edge TTS mp3 for each name in data/vocab/interview_names.txt (one by one).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

VOICE="${VOICE:-en-IN-NeerjaNeural}"

echo "Generating interview name samples with edge-tts voice: $VOICE"
echo "Output: data/name-samples/*.mp3"
python scripts/generate_interview_name_samples.py --voice "$VOICE" "$@"

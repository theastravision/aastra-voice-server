#!/usr/bin/env bash
# Quick check that main app imports (run on Salad after syncing code).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "No .venv — run: bash scripts/salad-run.sh --install"
  exit 1
fi

# shellcheck disable=SC1091
. .venv/bin/activate

echo "==> Verifying Python imports"
python -c "
from engines.demo_bot import _greeting_text
from engines.stt_filters import is_phantom_stt_text, is_substantive_utterance
from engines.tts_utils import is_speakable_text, ensure_pcm_s16le_bytes
from server import InterviewSession
from llm_worker import PhraseBuffer
from engines.hinglish_normalize import normalize_hinglish
assert is_phantom_stt_text('Thank you.')
assert not is_substantive_utterance('Thank you.')
assert is_substantive_utterance('I worked on REST APIs for two years.')
print('OK: all imports')
print('greeting sample:', _greeting_text('Test', 'en')[0][:40], '...')
"

echo "==> Done"

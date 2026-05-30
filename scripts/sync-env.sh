#!/usr/bin/env bash
# Upsert optimized voice-pipeline env keys into .env (safe to run every start).
# Called by scripts/run-all.sh on Ubuntu/Salad GPU hosts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"

upsert_env_key() {
  local key="$1"
  local val="$2"
  local file="$ENV_FILE"

  if [[ ! -f "$file" ]]; then
    touch "$file"
  fi

  # Escape sed replacement metacharacters in value
  local escaped
  escaped="$(printf '%s' "$val" | sed 's/[\\&|]/\\&/g')"

  if grep -qE "^${key}=" "$file" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
  else
    echo "${key}=${val}" >>"$file"
  fi
}

remove_env_key() {
  local key="$1"
  local file="$ENV_FILE"
  [[ -f "$file" ]] || return 0
  sed -i "/^${key}=/d" "$file"
}

dedupe_env_file() {
  local file="$ENV_FILE"
  [[ -f "$file" ]] || return 0
  python3 - "$file" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding='utf-8').splitlines()
entries: list[tuple[str | None, str]] = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or '=' not in stripped:
        entries.append((None, line))
        continue
    key = stripped.split('=', 1)[0].strip()
    entries.append((key, line))

seen: set[str] = set()
deduped: list[str] = []
for key, line in reversed(entries):
    if key is None:
        deduped.append(line)
    elif key not in seen:
        seen.add(key)
        deduped.append(line)
deduped.reverse()
path.write_text('\n'.join(deduped) + ('\n' if deduped else ''), encoding='utf-8')
PY
}

migrate_legacy_f5_keys() {
  remove_env_key F5_REF_AUDIO
  remove_env_key F5_REF_TEXT
}

sync_pipeline_env() {
  echo "Syncing voice-pipeline env keys → $ENV_FILE"

  migrate_legacy_f5_keys

  # ── STT: Silero VAD + single-pass faster-whisper ──────────────────────────
  upsert_env_key STT_PROVIDER whisper
  upsert_env_key STT_SILENCE_END_MS 900
  upsert_env_key STREAM_SILENCE_END_MS 900
  upsert_env_key SILERO_VAD_THRESHOLD 0.5
  upsert_env_key STT_VAD_SILENCE_MS 500
  upsert_env_key STT_MIN_SPEECH_MS 300
  upsert_env_key WHISPER_VAD_FILTER true
  upsert_env_key WHISPER_COMPUTE_TYPE float16
  upsert_env_key WHISPER_BEAM_SIZE 1
  upsert_env_key WHISPER_DEVICE cuda
  upsert_env_key WHISPER_MODEL distil-large-v3
  upsert_env_key STT_SILERO_TRIGGER_END_UTTERANCE false
  upsert_env_key STREAM_STT_MIN_CHARS 4
  upsert_env_key STT_UTTERANCE_MAX_SECS 30
  upsert_env_key STT_TRANSCRIBE_TIMEOUT_SECS 120

  # ── TTS: F5 English + Hinglish reference clips (no duplicate F5_REF_AUDIO) ─
  upsert_env_key TTS_PROVIDER f5
  upsert_env_key TTS_HINGLISH_ENGINE melotts
  upsert_env_key TTS_OUTPUT_SCRIPT roman
  upsert_env_key TTS_LLM_SCRIPT_STRICT true
  upsert_env_key MELOTTS_DEVICE cuda
  upsert_env_key MELOTTS_SPEED 1.0
  upsert_env_key MELOTTS_SPEAKER EN-IND
  upsert_env_key F5_MODEL F5TTS_v1_Base
  upsert_env_key F5_NFE_STEPS 12
  upsert_env_key F5_SWAY_COEF -1.0
  upsert_env_key F5_SPEED 1.0
  upsert_env_key F5_CROSS_FADE_DURATION 0.15
  upsert_env_key F5_DTYPE float16
  upsert_env_key F5_VOCODER vocos
  upsert_env_key F5_HINGLISH_SCRIPT roman
  upsert_env_key F5_REF_AUDIO_EN assets/voices/astra_ref.wav
  upsert_env_key F5_REF_TEXT_EN "Hello! My name is Astra. Please keep sharing your screen; you may check it. Whenever you are ready, we can begin the interview."
  upsert_env_key F5_REF_AUDIO_HINGLISH assets/voices/astra_ref_hinglish.wav
  upsert_env_key F5_REF_TEXT_HINGLISH "Namaste! Mera naam Astra hai. Kripya apna drishya-patal saanjha rakhna jaari rakhiye, aap jaanch kar sakte hain. Jab bhi aap taiyar hon, hum sakshatkar aarambh kar sakte hain."

  # ── LLM streaming + latency tuning ────────────────────────────────────────
  upsert_env_key OPENAI_MODEL gpt-4o-mini
  upsert_env_key OPENAI_MAX_COMPLETION_TOKENS 64
  upsert_env_key OPENAI_VOICE_TEMPERATURE 0.5
  upsert_env_key STREAM_LLM_MIN_WORDS 3
  upsert_env_key STREAM_LLM_NEXT_MIN_WORDS 5
  upsert_env_key INTERJECTION_TIMEOUT_MS 300
  upsert_env_key STREAM_LISTEN_IDLE_SECS 8
  upsert_env_key BARGE_IN_THRESHOLD 0.04

  # ── WebSocket / audio stream ─────────────────────────────────────────────
  upsert_env_key STREAM_ALLOW_PUBLIC true
  upsert_env_key STREAM_SAMPLE_RATE 16000
  upsert_env_key STREAM_CHUNK_MS 30
  upsert_env_key STREAM_STT_WINDOW_MS 600
  upsert_env_key TTS_OUTPUT_FORMAT wav

  # ── Server / interview defaults ────────────────────────────────────────────
  upsert_env_key HOST "*"
  upsert_env_key PORT 8000
  upsert_env_key ALLOW_PUBLIC_DEMO true
  upsert_env_key BOT_MODE interview
  upsert_env_key INTERVIEW_STRICT_MODE true
  upsert_env_key INTERVIEW_OPENING_ENABLED true
  upsert_env_key INTERVIEW_JOB_TITLE "Software Engineer"
  upsert_env_key DEMO_CANDIDATE_NAME Aashish

  dedupe_env_file
  echo "Pipeline env sync complete (duplicates removed, F5 refs split EN/Hinglish)."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  sync_pipeline_env
fi

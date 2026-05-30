# Salad par hi chalana (local machine ki zaroorat nahi)

Sab kuch Salad GPU container ke andar. Bot UI: **`/bot`**.

## 1) Pehli baar — install

```bash
cd /workspace/voice-server
# ya: cd ~/aastra-voice

chmod +x scripts/*.sh
bash scripts/salad-run.sh --install
```

## 2) `.env` — secrets append karo

Pehle `OPENAI_API_KEY` aur `HF_TOKEN` set karo (agar `.env` nahi hai to `cp .env.example .env`).

**Option A — script (recommended):**

```bash
bash scripts/salad-append-env.sh
```

Phir `.env` kholo aur sirf ye do lines apni keys se bharo:

```bash
nano .env
# OPENAI_API_KEY=sk-...
# HF_TOKEN=hf-...
```

**Option B — manual `>> .env`:**

```bash
cat >> .env << 'EOF'

# --- salad-append-env (do not duplicate) ---
OPENAI_API_KEY=sk-REPLACE_ME
HF_TOKEN=hf_REPLACE_ME
HOST=*
PORT=8000
ALLOW_PUBLIC_DEMO=true
BOT_MODE=interview
INTERVIEW_JOB_TITLE=Software Engineer
DEMO_CANDIDATE_NAME=Aashish
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_COMPLETION_TOKENS=64
OPENAI_VOICE_TEMPERATURE=0.5
STT_PROVIDER=whisper_chunk
TTS_PROVIDER=parler
PARLER_MODEL_ID=ai4bharat/indic-parler-tts
PARLER_DEVICE=cuda
PARLER_DTYPE=float16
PARLER_MAX_NEW_TOKENS=0
STREAM_LLM_MIN_WORDS=3
STREAM_LISTEN_IDLE_SECS=8
STREAM_STT_MIN_CHARS=8
TTS_OUTPUT_FORMAT=wav
PARLER_CAPTION_HI=Divya speaks in a clear Indian Hindi accent with a calm, professional, moderate pace. Very clear audio, close recording, no background noise.
PARLER_CAPTION_EN=Mary speaks with a clear Indian English accent, calm professional tone, moderate pace. Very clear audio, close recording, no background noise.
WHISPER_MODEL=large-v3
WHISPER_LANGUAGE=auto
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WHISPER_BEAM_SIZE=1
WHISPER_INITIAL_PROMPT=Hinglish conversation mixing Hindi and English. हिंदी और अंग्रेज़ी मिश्रित बातचीत।
STREAM_ALLOW_PUBLIC=true
STREAM_SAMPLE_RATE=16000
STREAM_CHUNK_MS=30
STREAM_STT_WINDOW_MS=600
EOF
```

Hugging Face par model accept karo: https://huggingface.co/ai4bharat/indic-parler-tts

## 3) Har baar start

```bash
bash scripts/salad-run.sh
```

Models warm hone tak wait (~1–3 min pehli baar):

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

## 4) Bahar se open karna (ngrok)

```bash
bash scripts/salad-run.sh --ngrok
```

Ya alag terminal:

```bash
ngrok http 8000
```

Browser: **`https://YOUR-NGROK-URL/bot`**

Salad Container Gateway use karte ho to public URL + `/bot`.

## React UI (`/interview`) — Salad par build

**Pehli baar** (Node + build, `--install` ke andar bhi hota hai):

```bash
cd /workspace/voice-server
sudo apt-get update && sudo apt-get install -y nodejs npm   # agar npm missing ho
bash scripts/build-interview-ui.sh
bash scripts/salad-run.sh
```

Sirf React dubara build:

```bash
bash scripts/salad-run.sh --build-ui
bash scripts/stop-voice.sh
bash scripts/run-demo-background.sh
# ya: bash scripts/salad-run.sh
```

Browser (ngrok / Salad gateway):

- **React:** `https://YOUR-PUBLIC-URL/interview/` (trailing slash; `/interview` redirects)
- **HTML bot:** `https://YOUR-PUBLIC-URL/bot`

`dist/` nahi bana to `/interview` automatically `/bot` par redirect karega.

## URLs (Salad container ke andar)

| Kya | URL |
|-----|-----|
| Bot (HTML) | `http://127.0.0.1:8000/bot` |
| Interview (React) | `http://127.0.0.1:8000/interview/` |
| Health | `http://127.0.0.1:8000/health` |
| WebSocket voice | `wss://YOUR-PUBLIC-HOST/ws/voice` |

## Band karna

```bash
bash scripts/stop-voice.sh
```

## Local scripts (optional — Salad par mat chalao)

`scripts/run-local-dev.sh` sirf apni laptop ke liye hai. Salad par use **nahi** karna.

## TTS error fix

`.env` me `PARLER_MAX_NEW_TOKENS=0` hona chahiye (512 se streaming TTS fail ho sakta hai).

```bash
grep PARLER_MAX_NEW_TOKENS .env || echo 'PARLER_MAX_NEW_TOKENS=0' >> .env
bash scripts/stop-voice.sh && bash scripts/salad-run.sh
```

## Phantom STT / mic sensitivity (HAR fixes)

After syncing this tree, redeploy on Salad:

```bash
bash scripts/verify-imports.sh
bash scripts/build-interview-ui.sh
bash scripts/stop-voice.sh
bash scripts/salad-run.sh --ngrok
```

`.env` should include:

- `PARLER_MAX_NEW_TOKENS=0`
- `STREAM_LLM_MIN_WORDS=3` (TTS waits for full sentences, not commas)
- `STREAM_LISTEN_IDLE_SECS=8` (nudge after silence)
- `STREAM_STT_MIN_CHARS=8` (drop tiny Whisper hallucinations)

**Acceptance:** silent mic does not produce `stt_final: "Thank you."`; after ~8s idle you hear the repeat-question nudge in your selected language.

## Multi-turn `/interview` test (WS-only)

1. `bash scripts/build-interview-ui.sh` then `bash scripts/salad-run.sh`
2. Open `https://YOUR-NGROK/interview/`
3. Pick **English** (or Hindi/Hinglish) → **Start call**
4. Network tab: only `GET /api/v1/demo/config` + `WS /ws/voice` — **no** `POST /api/v1/demo/start`
5. WS: `config` with `greet:true` → greeting `turn_start` → `audio_config` → **binary PCM** → `turn_end` → then you speak
6. Second turn: same sequence, no `TTS failed`
7. `curl -s http://127.0.0.1:8000/health` → `models_ready: true`

English mode uses a technical STT prompt (software development, APIs, etc.) to reduce mishears like “fire development”.

## Latency (realistic)

Self-hosted **Whisper + Parler + OpenAI** on Salad GPU cannot do literal **70ms** speech-to-speech. Tuned defaults (`STREAM_STT_WINDOW_MS=600`, `WHISPER_BEAM_SIZE=1`, faster client VAD) target the fastest safe multi-turn behavior. For sub-second round-trip you need streaming cloud STT/TTS or pre-recorded clips.

Optional faster STT (dev only, less accurate): `WHISPER_MODEL=distil-large-v3` or `base` in `.env`.

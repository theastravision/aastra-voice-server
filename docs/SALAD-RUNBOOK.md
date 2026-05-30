# Salad GPU runbook — Aastra voice server

**Salad / remote GPU only** — local PC par kuch chalane ki zaroorat nahi. Bot UI: `/bot`.

Hindi quick guide: [SALAD-ONLY.md](SALAD-ONLY.md)

Assumes code at `/workspace/voice-server` or `~/aastra-voice`.

## Quick: one script (recommended)

```bash
cd /workspace/voice-server
chmod +x scripts/*.sh

# .env + Salad defaults (append once):
bash scripts/salad-append-env.sh
# Then edit .env: OPENAI_API_KEY, HF_TOKEN

# First time only:
bash scripts/salad-run.sh --install

# Every time (stop + start + wait for health):
bash scripts/salad-run.sh

# With ngrok tunnel:
bash scripts/salad-run.sh --ngrok
```

Uses **Indic Parler-TTS** only. Technical interviewer mode (`BOT_MODE=interview`).

---

## 1. Stop any old process

```bash
cd ~/aastra-voice
bash scripts/stop-voice.sh
```

## 2. Create / append `.env`

Accept the model license first: https://huggingface.co/ai4bharat/indic-parler-tts

**Append (keeps existing keys):**

```bash
cd /workspace/voice-server
bash scripts/salad-append-env.sh
nano .env   # set OPENAI_API_KEY and HF_TOKEN
```

**Or full file from scratch:**

```bash
cd /workspace/voice-server
cat > .env << 'EOF'
OPENAI_API_KEY=sk-REPLACE_ME
HF_TOKEN=hf_REPLACE_ME
VOICE_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_COMPLETION_TOKENS=128
OPENAI_VOICE_TEMPERATURE=0.5
CHAT_HISTORY_MAX_TURNS=8

BOT_MODE=interview
INTERVIEW_JOB_TITLE=Software Engineer
STT_PROVIDER=whisper_chunk
TTS_PROVIDER=parler
PARLER_DEVICE=cuda
PARLER_DTYPE=float16
PARLER_CAPTION_HI=Divya speaks in a calm, clear, moderate-paced professional tone. The recording has very clear audio with no background noise.
PARLER_CAPTION_EN=Mary speaks with a calm, professional tone at a moderate pace. Very clear audio, close recording, no background noise.
PARLER_MAX_NEW_TOKENS=0
STREAM_LLM_MIN_WORDS=2

WHISPER_MODEL=large-v3
WHISPER_LANGUAGE=auto
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WHISPER_BEAM_SIZE=5
WHISPER_INITIAL_PROMPT="Hinglish conversation mixing Hindi and English. हिंदी और अंग्रेज़ी मिश्रित बातचीत।"

TTS_OUTPUT_FORMAT=wav

STREAM_ALLOW_PUBLIC=true
STREAM_SAMPLE_RATE=16000
STREAM_CHUNK_MS=30
STREAM_STT_WINDOW_MS=1500
STREAM_LLM_MIN_WORDS=4

HOST=*
PORT=8000
ALLOW_PUBLIC_DEMO=true
DEMO_CANDIDATE_NAME=Aashish
EOF
```

Replace `sk-REPLACE_ME` and `hf_REPLACE_ME`.

## 3. Install dependencies (first time only)

```bash
cd ~/aastra-voice
chmod +x scripts/*.sh
bash scripts/install-demo.sh
```

This installs PyTorch, `requirements.txt`, and runs `install-parler.sh`.

## 4. Download / warm models

```bash
cd ~/aastra-voice
source .venv/bin/activate
bash scripts/download-models.sh
```

## 5. Start server in background

```bash
cd ~/aastra-voice
PORT=8000 HOST='*' bash scripts/run-demo-background.sh
```

Wait until models are ready:

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
# "models_ready": true
```

Or:

```bash
bash scripts/verify-ngrok.sh
```

## 6. Expose with ngrok

**Port must match `PORT` in `.env` (8000):**

```bash
ngrok http 8000
```

Open the HTTPS URL:

- Health: `https://YOUR_SUBDOMAIN.ngrok-free.app/health`
- Bot UI: `https://YOUR_SUBDOMAIN.ngrok-free.app/bot`

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| **ERR_NGROK_3004** | Server not listening. `ngrok http 8000` when `PORT=8000`. `curl http://127.0.0.1:8000/health`. |
| `parler-tts not installed` | `bash scripts/install-parler.sh` |
| Gated model / 401 on download | Set `HF_TOKEN`; accept license on Hugging Face |
| Health stuck `models_ready: false` | `tail -f voice-server.log` — Parler warmup may take several minutes first run |
| WebSocket fails on `/bot` | REST fallback; check `STREAM_ALLOW_PUBLIC=true` |

See [PARLER_TTS.md](PARLER_TTS.md) for caption tuning.

## Stop

```bash
cd ~/aastra-voice
bash scripts/stop-voice.sh
```

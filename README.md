# AastraaHR Voice Server

Self-hosted **Indic Parler-TTS** (AI4Bharat) for Hindi, English, and Hinglish, plus **faster-whisper** STT and a **GPT conversational** turn API.

**Real-time streaming:** see [STREAMING.md](STREAMING.md) for `/ws/voice` (PCM duplex, OSS Whisper + Parler, OpenAI LLM stream).

**Languages:** Hindi, English, and Hinglish (mixed). OpenAI is the only paid API.

**TTS setup:** [docs/PARLER_TTS.md](docs/PARLER_TTS.md) — Hugging Face token, captions, Salad install.

**Training data & fine-tuning:** [docs/DATASETS_AND_TRAINING.md](docs/DATASETS_AND_TRAINING.md)

Deploy to [Salad Cloud](https://docs.salad.com/container-engine/explanation/infrastructure-platform/networking) or any CUDA 12 GPU host.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health probe |
| WS | `/ws/audio` | Bearer `VOICE_API_KEY` | Django `XyzAudioProvider` protocol (`tts` / `stt` events) |
| POST | `/api/v1/transcribe` | Bearer | Multipart audio → transcript |
| POST | `/api/v1/tts` | Bearer | JSON `{text, voice?, lang?}` → WAV/MP3 |
| POST | `/api/v1/voice-turn` | Bearer | Multipart audio + optional `history` JSON → STT + GPT + TTS |

## Local run (CPU/GPU)

```bash
cd apps/voice-server
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
bash scripts/install-parler.sh
cp .env.example .env        # OPENAI_API_KEY, HF_TOKEN, VOICE_API_KEY
export $(grep -v '^#' .env | xargs)
python -m uvicorn main:app --host 0.0.0.0 --port 8888
```

On Windows without GPU, set `WHISPER_DEVICE=cpu`, `PARLER_DEVICE=cpu`, and `WHISPER_COMPUTE_TYPE=int8`.

## Salad quick start

```bash
cd ~/aastra-voice
bash scripts/salad-run.sh --install
bash scripts/salad-run.sh
```

See [docs/SALAD-RUNBOOK.md](docs/SALAD-RUNBOOK.md).

## Docker build

```bash
docker build -t your-registry/aastra-voice:latest apps/voice-server
docker push your-registry/aastra-voice:latest
```

## Salad Cloud deployment

1. **Container group** → GPU class with **≥ 16 GB VRAM** (Parler ~1B + Whisper large-v3).
2. **Environment variables:**

   | Variable | Example |
   |----------|---------|
   | `VOICE_API_KEY` | shared secret |
   | `OPENAI_API_KEY` | `sk-...` |
   | `HF_TOKEN` | `hf_...` (accept [model license](https://huggingface.co/ai4bharat/indic-parler-tts)) |
   | `TTS_PROVIDER` | `parler` |
   | `WHISPER_MODEL` | `large-v3` |
   | `PARLER_CAPTION_HI` / `PARLER_CAPTION_EN` | calm interviewer captions |

Hinglish uses per-script Parler routing (EN + HI segments). See [VOICE_TUNING.md](VOICE_TUNING.md).

## Voice tuning

See [VOICE_TUNING.md](./VOICE_TUNING.md) and [docs/PARLER_TTS.md](docs/PARLER_TTS.md).

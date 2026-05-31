# svara-TTS (Indic languages)

English interview speech uses **F5-TTS** (unchanged). Hindi, Hinglish, and other Indic languages use **[svara-tts-v1](https://huggingface.co/kenpath/svara-tts-v1)** via a **separate sidecar process** (`.venv-svara` on port 8080).

F5 and svara **cannot share one Python venv** — vLLM 0.17+ needs PyTorch 2.10 while F5 uses cu124 torch. Mixing them breaks CUDA/NVRTC and warmup.

## Requirements

- NVIDIA GPU with **24GB+ VRAM** recommended when running F5 + svara together
- Git
- Main `.venv` for F5 + FastAPI (`bash scripts/install-f5-tts.sh`)
- Separate `.venv-svara` for svara (`bash scripts/install-svara-tts.sh`)

## Install

```bash
# Main server (F5, Whisper, FastAPI)
bash scripts/install-f5-tts.sh

# svara sidecar (separate venv — do NOT pip install into main .venv)
bash scripts/install-svara-tts.sh
```

This clones `Kenpath/svara-tts-inference` into `vendor/svara-tts-inference` and installs `requirements-svara-sidecar.txt` into `.venv-svara` only.

## Configuration (`.env`)

```env
TTS_INDIC_ENGINE=svara
SVARA_TTS_URL=http://127.0.0.1:8080
SVARA_TTS_TIMEOUT_SEC=120
SVARA_MODEL=kenpath/svara-tts-v1
SVARA_VLLM_GPU_MEMORY_UTILIZATION=0.50
SVARA_SNAC_DEVICE=cuda
SVARA_DEFAULT_VOICE=Hindi (Female)
SVARA_HINGLISH_VOICE=Hindi (Female)
```

Lower `SVARA_VLLM_GPU_MEMORY_UTILIZATION` if F5 and svara share one GPU and you hit OOM.

Optional emotion tag for clearer proper nouns:

```env
SVARA_EMOTION_TAG=<clear>
```

## Start / stop

```bash
# Start both (svara sidecar + voice server)
bash scripts/run-demo-background.sh

# Or manually:
bash scripts/run-svara-sidecar.sh --background
bash scripts/wait-svara-health.sh
bash scripts/run-demo.sh

# Stop both
bash scripts/stop-voice.sh
```

## Routing

| Language | Engine |
|----------|--------|
| `en` | F5 (`astra` voice) |
| `hi`, `hinglish`, `ta`, `bn`, … | svara HTTP sidecar |

Voices are defined in [`data/voices.json`](../data/voices.json). Svara voices use `"engine": "svara"` and `"svara_speaker": "Hindi (Female)"`.

## Health check

```bash
curl http://127.0.0.1:8080/health                    # svara sidecar (must be HTTP 200)
curl http://127.0.0.1:8888/api/v1/demo/config        # voice server (Salad default PORT=8888)
```

Required `.env` for Indic routing:

```env
TTS_INDIC_ENGINE=svara
SVARA_TTS_URL=http://127.0.0.1:8080
PORT=8888
```

Until `curl :8080/health` returns 200, Hindi/Hinglish **falls back to F5** (robotic cloned voice).

### Verify routing in logs

After restart, grep the voice-server log:

```bash
grep -E 'falling back to F5|TTS backend=' voice-server.log
```

| Log line | Meaning |
|----------|---------|
| `TTS backend=svara reply_script=hi` | Indic turn uses native svara voice |
| `TTS backend=f5 reply_script=hi` | Sidecar down or `TTS_INDIC_ENGINE` not `svara` |
| `svara unavailable (...); falling back to F5` | Health check failed — start sidecar |

WebSocket `turn_start` events include `tts_backend` (`f5` or `svara`) for browser devtools.

`GET /api/v1/demo/config` returns:

- `tts_indic_engine`: `svara`
- `svara_url`: configured sidecar URL
- `svara_ready`: `true` when sidecar health + warmup succeeded
- `svara_error`: error message if sidecar unreachable

## Supported svara languages

Hindi, Bengali, Marathi, Telugu, Kannada, Bhojpuri, Magahi, Chhattisgarhi, Maithili, Assamese, Bodo, Dogri, Gujarati, Malayalam, Punjabi, Tamil, Nepali, Sanskrit, Odia, Manipuri — mapped in `config.SVARA_SPEAKER_BY_LANG`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `svara_ready: false`, sidecar unreachable | `bash scripts/install-svara-tts.sh` then `bash scripts/run-svara-sidecar.sh --background` |
| F5 `libnvrtc-builtins.so.13.0` after svara install in main venv | `pip uninstall -y vllm flashinfer-python snac torchcodec` in `.venv`, reinstall F5 torch, use `.venv-svara` only for svara |
| CUDA OOM on sidecar warmup | Lower `SVARA_VLLM_GPU_MEMORY_UTILIZATION` to `0.40` |
| Indic still sounds like F5 clone | Confirm `TTS_INDIC_ENGINE=svara` and sidecar healthy |
| English changed | English always uses F5; check `reply_script=en` in logs |
| Port 8080 in use | Change `SVARA_TTS_URL` and `SVARA_PORT` |

## Text preparation

Svara receives Devanagari/mixed script with ellipsis pauses — **not** phonetic hyphenation. See [`engines/tts_svara_pipeline.py`](../engines/tts_svara_pipeline.py).

## Architecture

```
.venv (port 8000)          .venv-svara (port 8080)
FastAPI + F5 + Whisper  →  HTTP POST /v1/audio/speech  →  Kenpath api/server.py + vLLM
```

Main server never imports vLLM; it only calls the sidecar over HTTP.

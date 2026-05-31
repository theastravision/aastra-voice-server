# svara-TTS (Indic languages)

English interview speech uses **F5-TTS** (unchanged). Hindi, Hinglish, and other Indic languages use **embedded [svara-tts-v1](https://huggingface.co/kenpath/svara-tts-v1)** from Kenpath.

## Requirements

- NVIDIA GPU with **24GB+ VRAM** recommended when running F5 + svara together
- CUDA drivers and PyTorch already installed (see `scripts/install-f5-tts.sh`)
- Git

## Install

```bash
bash scripts/install-svara-tts.sh
```

This clones `Kenpath/svara-tts-inference` into `vendor/svara-tts-inference` and installs `requirements-svara.txt`.

## Configuration (`.env`)

```env
TTS_INDIC_ENGINE=svara
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

## Routing

| Language | Engine |
|----------|--------|
| `en` | F5 (`astra` voice) |
| `hi`, `hinglish`, `ta`, `bn`, … | svara |

Voices are defined in [`data/voices.json`](../data/voices.json). Svara voices use `"engine": "svara"` and `"svara_speaker": "Hindi (Female)"`.

## Health check

After restart, `GET /api/v1/demo/config` returns:

- `tts_indic_engine`: `svara`
- `svara_ready`: `true` when warmup succeeded
- `svara_error`: error message if install/warmup failed

## Supported svara languages

Hindi, Bengali, Marathi, Telugu, Kannada, Bhojpuri, Magahi, Chhattisgarhi, Maithili, Assamese, Bodo, Dogri, Gujarati, Malayalam, Punjabi, Tamil, Nepali, Sanskrit, Odia, Manipuri — mapped in `config.SVARA_SPEAKER_BY_LANG`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `svara_ready: false`, vendor missing | Run `bash scripts/install-svara-tts.sh` |
| CUDA OOM on warmup | Lower `SVARA_VLLM_GPU_MEMORY_UTILIZATION` to `0.40` |
| Indic still sounds like F5 clone | Confirm `TTS_INDIC_ENGINE=svara` and restart server |
| English changed | English always uses F5; check `reply_script=en` in logs |

## Text preparation

Svara receives Devanagari/mixed script with ellipsis pauses — **not** phonetic hyphenation. See [`engines/tts_svara_pipeline.py`](../engines/tts_svara_pipeline.py).

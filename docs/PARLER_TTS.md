# Indic Parler-TTS (AI4Bharat)

The voice server uses **[ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts)** as the **only** TTS engine (Apache 2.0, ~0.94B parameters).

## Prerequisites

1. Create a [Hugging Face](https://huggingface.co) account.
2. Open [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts) and **accept the model conditions** (gated repo).
3. Create an access token: Settings → Access Tokens → Read.
4. Add to `.env`:

```env
HF_TOKEN=hf_your_token_here
TTS_PROVIDER=parler
```

## Install

Inside the project venv (after PyTorch):

```bash
bash scripts/install-parler.sh
```

Or manually:

```bash
pip install "transformers>=4.46.0" accelerate huggingface_hub
pip install git+https://github.com/huggingface/parler-tts.git
```

## Captions (voice control)

Parler takes two inputs:

1. **Transcript** — the text to speak.
2. **Caption** — how it should sound.

Set in `.env`:

```env
PARLER_CAPTION_HI=Divya speaks in a clear Indian Hindi accent with a calm, professional, moderate pace. Very clear audio, close recording, no background noise.
PARLER_CAPTION_EN=Mary speaks with a clear Indian English accent, calm professional tone, moderate pace. Very clear audio, close recording, no background noise.
PARLER_MAX_NEW_TOKENS=0
STREAM_LLM_MIN_WORDS=2
```

### Hindi recommended speakers

| Speaker | Notes |
|---------|--------|
| Rohit | Male, recommended |
| Divya | Female, recommended (default caption) |
| Aman | Male |
| Rani | Female |

Include the speaker name in the caption for consistency across turns.

## Hinglish

Mixed Latin + Devanagari replies are split by script; each segment uses the matching caption (`PARLER_CAPTION_EN` or `PARLER_CAPTION_HI`).

## Latency tips

- First reply is slower until models are warmed (`/health` → `models_ready: true`).
- Shorter sentences = faster per-chunk synthesis.
- Future: enable Parler [streaming inference](https://github.com/huggingface/parler-tts/blob/main/INFERENCE.md) (`ParlerTTSStreamer`, `torch.compile`).

## Verify

```bash
source .venv/bin/activate
python -c "from engines.parler_tts import parler_available, warmup; print(parler_available()); warmup()"
```

## Salad

```bash
bash scripts/salad-run.sh --install
bash scripts/salad-run.sh
```

See [SALAD-RUNBOOK.md](SALAD-RUNBOOK.md).

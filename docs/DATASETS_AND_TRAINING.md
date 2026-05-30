# Datasets and fine-tuning (English / Hindi / Hinglish)

This voice server **does not ship 100 million audio files** in the repository. Instead:

1. **Runtime** uses pre-trained **Whisper** (STT) and **Indic Parler-TTS** (TTS).
2. **You** download open datasets and fine-tune offline, then point `.env` at your checkpoints.

Catalog: [`datasets/oss_manifest.json`](../datasets/oss_manifest.json)

---

## What “100 million samples” means in practice

| Layer | Pre-trained scale | What you add |
|-------|-------------------|--------------|
| **Whisper** | ~680k hours multilingual (OpenAI) | Fine-tune on 500–5k+ hours Hindi + Hinglish clips |
| **Indic Parler-TTS** | ~0.94B, 21 languages | Caption-tuned delivery; optional fine-tune on Indic corpora |
| **Combined Indic corpora** | IndicVoices, IndicTTS, Common Voice | Can reach **10M–100M utterances** if you merge corpora on disk |

“100 million” usually means **total training examples across merged datasets**, not a single download button. Preparation (resample to 16 kHz, text normalization, train/val split) is a separate GPU training job.

---

## Recommended open datasets

### STT (speech → text)

| Dataset | ~Scale | Languages | Link |
|---------|--------|-----------|------|
| AI4Bharat IndicVoices | Very large | Hindi + Indic | [Hugging Face](https://huggingface.co/datasets/ai4bharat/IndicVoices) |
| IndicVoices-R | Large | Cleaner Hindi labels | [Hugging Face](https://huggingface.co/datasets/ai4bharat/IndicVoices-R) |
| Mozilla Common Voice 17 | Medium per lang | `hi`, `en` | [Hugging Face](https://huggingface.co/datasets/mozilla-foundation/common_voice_17_0) |
| MUCS / Hinglish challenges | Small | Code-mixed | Search “MUCS Hinglish ASR” |

### TTS (text → speech)

| Dataset | ~Scale | Use |
|---------|--------|-----|
| AI4Bharat IndicTTS | Large (Hindi listed ~10M+ lines in docs) | Train MeloTTS / VITS / custom Kokoro |
| LJSpeech | 13k utterances | English baseline |
| OpenSLR Hindi | Medium | Hindi TTS |

---

## Plug fine-tuned models into this server

After training, set in `.env`:

```env
# Use local faster-whisper CTranslate2 folder instead of hub name
WHISPER_MODEL=large-v3
WHISPER_MODEL_PATH=/data/checkpoints/whisper-hi-hinglish-ct2

# Optional: future MeloTTS / custom checkpoint (when wired)
# TTS_FINETUNE_PATH=/data/checkpoints/melo-hindi
```

`WHISPER_MODEL_PATH` overrides the Hugging Face hub id when the path exists (see `engines/whisper_stt.py`).

Restart:

```bash
bash scripts/stop-voice.sh
PORT=8000 HOST='*' bash scripts/run-demo-background.sh
```

---

## Training pointers (offline)

### Whisper fine-tune

- Tooling: [Hugging Face transformers](https://huggingface.co/docs/transformers/model_doc/whisper), [faster-whisper CT2 conversion](https://github.com/SYSTRAN/faster-whisper), or [whisper-finetune](https://github.com/vikhyatkrishnan/whisper-finetune) community recipes.
- Data: 16 kHz mono WAV + transcript TSV.
- Hinglish: mix English and Hindi rows; keep `language=None` at inference or use custom prompt.

### TTS fine-tune

- **Kokoro**: limited public fine-tune docs; most teams use **MeloTTS**, **Coqui TTS (VITS)**, or **StyleTTS2** on IndicTTS then add a new `TTS_PROVIDER`.
- **Parler-TTS**: fine-tune or swap `PARLER_MODEL_ID` to a custom checkpoint after training on IndicTTS / IndicVoices-derived speech.

---

## Devanagari languages — same flow or not?

**Same script ≠ same language.** These languages often use **Devanagari** but have different grammar and pronunciation:

| Language | Script | Whisper (`whisper_iso`) | This repo’s TTS today |
|----------|--------|-------------------------|------------------------|
| Hindi | Devanagari | `hi` | Kokoro `hf_alpha` (good) |
| Marathi | Devanagari | `mr` | Hindi pipeline (approximate) |
| Nepali | Devanagari | `ne` | Hindi pipeline (approximate) |
| Sanskrit | Devanagari | `sa` | Hindi pipeline (poor) |
| Maithili, Dogri | Devanagari | `mai`, `doi` | Needs training |

### Can one trained model cover all Devanagari languages?

| Component | Same model? | Notes |
|-----------|-------------|-------|
| **Your pipeline** (`/bot`, `/ws/voice`) | **Yes** | Same WebSocket + STT → LLM → TTS flow for any language you add |
| **Whisper zero-shot** | **Partial** | Picks `hi` / `mr` / `ne` by detection; quality varies |
| **Whisper fine-tuned** | **Yes, if you train multi-lingual** | One model with language tags on 500+ hours per language |
| **Kokoro HI voice** | **No for native quality** | Trained for Hindi, not Marathi/Nepali — sounds “Hindi-accented” |
| **Custom TTS per language** | **Best** | Fine-tune one checkpoint per language, or multi-speaker Indic TTS |

**Practical recommendation:**

- **Hindi + English + Hinglish** (your target): fine-tune Whisper on IndicVoices + Hinglish sets; keep Kokoro or train MeloTTS on IndicTTS Hindi; use `hinglish_tts.py` script splitting for replies.
- **Other Devanagari languages**: add STT fine-tune data for `mr`/`ne`/etc.; add a TTS checkpoint per language; extend `engines/indic_languages.py` and `pick_reply_script()` — flow stays the same.

Metadata helper: [`engines/indic_languages.py`](../engines/indic_languages.py)

---

## Hinglish vocab CSVs (`data/vocab/`)

Text-only corpora used to bootstrap Hinglish **lexicon coverage** (not a substitute for real human speech):

| File | Format | Use |
|------|--------|-----|
| `hinglish_words.csv` | `word,frequency` | Filtered lexicon → Whisper prompt bias, normalize map, stopwords |
| `hinglish_conversations.csv` | `input,output` | Cleaned utterances → synthetic F5 audio for Whisper fine-tune |

Scrape more conversation rows:

```bash
python scrape_vocabs.py
```

### 1. Export runtime/training artifacts

```bash
python training/export_vocab_artifacts.py
# or POST /api/v1/training/hinglish/export-artifacts
```

Writes under `data/vocab/`:

- `hinglish_normalize.generated.json` — spelling variants for F5-TTS
- `whisper_hinglish_prompt.txt` — sampled Whisper `initial_prompt` (auto-loaded when present)
- `hinglish_particles.txt` — high-frequency function words

### 2. Synthesize Hinglish STT corpus (F5 → 16 kHz WAV)

Requires F5-TTS installed and GPU recommended:

```bash
python training/synth_hinglish_corpus.py --max-rows 5000 --voice-id astra
# or POST /api/v1/training/hinglish/synthesize
```

Output:

- `data/training/hinglish/wavs/*.wav`
- `data/training/hinglish/manifest.tsv`
- `data/training/hinglish/f5_text_corpus.txt` (text side for future F5 fine-tune)
- `data/training/hinglish/synth_state.json` (resume checkpoint)

Config (`.env`):

```env
HINGLISH_VOCAB_DIR=data/vocab
HINGLISH_SYNTH_MAX_ROWS=5000
HINGLISH_SYNTH_VOICE_ID=astra
```

### 3. Merge with real audio (recommended)

Synthetic F5 speech teaches code-mixed **vocabulary**; IndicVoices / Common Voice adds **acoustic diversity**:

```bash
python training/merge_manifests.py hinglish hi
# → data/training/hinglish/manifest_merged.tsv
```

Then fine-tune Whisper on the merged manifest via the training UI or:

```bash
python training/run_whisper_finetune.py --language hinglish --job-id <uuid>
```

### Loader module

[`engines/hinglish_vocab.py`](../engines/hinglish_vocab.py) — shared filter/clean helpers used by synth + export scripts.

---

## Download helpers

```bash
# List catalog
cat datasets/oss_manifest.json

# Hugging Face example (requires: pip install huggingface_hub)
bash scripts/download-datasets.sh --list
bash scripts/download-datasets.sh --sample-hi   # small Common Voice Hindi slice
```

---

## See also

- [VOICE_TUNING.md](../VOICE_TUNING.md) — runtime knobs
- [STREAMING.md](../STREAMING.md) — `/ws/voice`
- [DEMO-SETUP.md](../DEMO-SETUP.md) — Salad install

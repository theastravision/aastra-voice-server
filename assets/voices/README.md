# Reference voice clips for F5-TTS speaker conditioning.

## Astra default voice (important)

Do **not** use the old F5 demo clip (`basic_ref_en.wav` / “Some call me nature…”). That audio is merged into every synthesis.

Generate a clean 5–10 s reference using **Neerja** (Microsoft `en-IN-NeerjaNeural` — clear Indian English, works well for English + Hindi/Hinglish):

```bash
pip install edge-tts
python scripts/setup_ref_audio.py --force
```

**Hinglish bilingual ref (12–14 s, recommended for Devanagari TTS):**

```bash
python scripts/setup_ref_audio.py --hinglish-bilingual --force
```

Set voice `astra_hinglish` in WebSocket config or `F5_REF_AUDIO=assets/voices/astra_ref_hinglish.wav`.

Optional override: `ASTRA_EDGE_TTS_VOICE=en-IN-NeerjaNeural` in `.env`

Set `.env` to match the transcript:

```env
F5_REF_TEXT=Hello, I am Astra. I will conduct your technical interview today.
```

Restart the voice server after replacing the WAV.

## Zero-shot voice cloning (TTS)

Each named voice in `data/voices.json` needs:
- `ref_audio` — 5–10 s clean mono WAV (24 kHz preferred)
- `ref_text` — exact transcript of that clip

Voices are selected in the Interview UI or via WebSocket config:

```json
{"type":"config","voice_id":"divya","language":"hi","greet":true}
```

## Import Kokoro-format Hindi dataset

```powershell
cd apps\voice-server
python training/import_kokoro_dataset.py `
  --input "C:\Users\cogni\Downloads\kokoro - hindi-dataset" `
  --language hi `
  --voice-name Divya `
  --start-whisper-job
```

This will:
1. Ingest all clips into `data/training/hi/` for Whisper STT fine-tuning
2. Register **Divya** as a TTS voice (best 5–10 s clip)
3. Queue a background Whisper training job

## Upload via UI

Open `/interview` → **Training** tab → upload WAV/MP3/ZIP or paste dataset path.

## STT fine-tuned models

After training completes, `data/models.json` maps `hi` / `en` / `hinglish` to CTranslate2 folders under `data/checkpoints/`. The STT worker loads the matching checkpoint when the interview language is set.

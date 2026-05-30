# Voice & STT tuning (F5-TTS + Devanagari Hinglish)

## Recommended `.env` (Salad / GPU)

```env
BOT_MODE=interview
INTERVIEW_JOB_TITLE=Software Engineer
TTS_PROVIDER=f5
STT_PROVIDER=whisper_chunk
WHISPER_MODEL=base
WHISPER_LANGUAGE=auto

# Devanagari Hinglish TTS pipeline
TTS_OUTPUT_SCRIPT=devanagari
TTS_HINGLISH_ENGINE=f5_devanagari
F5_HINGLISH_SCRIPT=devanagari
F5_CFG_STRENGTH=2.2
F5_NFE_STEPS=22
F5_SPEED=0.84
F5_REF_AUDIO=assets/voices/astra_ref_hinglish.wav
```

Install: `bash scripts/install-f5-tts.sh` then `pip install indic-transliteration`.

## Bot language selector (`/interview`)

| UI choice | STT | LLM output | TTS preprocessing |
|-----------|-----|------------|-------------------|
| English | `language=en` | Latin English | No transliteration |
| Hindi | `language=hi` | Devanagari + Latin tech terms | Hindi → Devanagari |
| Hinglish | auto + vocab prompt | Mixed Devanagari/Latin | Token classify + transliterate |
| Auto | Detect | Follow detected script mode | Per turn |

## LLM-first Devanagari (skip redundant TTS conversion)

When `TTS_DEVANAGARI_SOURCE=llm` and `TTS_LLM_SCRIPT_STRICT=true`:

- Frontend language (`en` / `hi` / `hinglish`) **strictly couples** to GPT output script
- GPT writes Devanagari directly for Hindi/Hinglish sessions
- TTS runs **normalize-only fast path** when text is already compliant (~1 ms)
- One GPT retry if script validation fails; pipeline transliteration is fallback only

```env
TTS_DEVANAGARI_SOURCE=llm
TTS_LLM_SCRIPT_STRICT=true
```

## Devanagari pipeline

1. **Spell normalize** — `engines/hinglish_normalize.py` + `data/vocab/hinglish_normalize.generated.json`
2. **Token classify** — English tech terms stay Latin; Hindi particles → Devanagari via ITRANS
3. **F5 synthesize** — bilingual ref clip + tunable `F5_CFG_STRENGTH`

Debug text:

```bash
python scripts/preprocess_tts_text.py \
  --text "Shuru karne se pehle, screen share on rakhein." \
  --mode devanagari --json
```

Export vocab artifacts first:

```bash
python training/export_vocab_artifacts.py
```

## Bilingual reference audio (10–15 s)

```bash
pip install edge-tts
python scripts/setup_ref_audio.py --hinglish-bilingual --force
# Optional mixed Devanagari registry text:
python scripts/setup_ref_audio.py --hinglish-bilingual --devanagari-ref-text --force
```

Use voice `astra_hinglish` in `data/voices.json` or set `F5_REF_AUDIO=assets/voices/astra_ref_hinglish.wav`.

## XTTS fallback (Astra voice clone)

If F5 Devanagari quality is weak on conjuncts:

```bash
bash scripts/install-xtts.sh
```

```env
TTS_HINGLISH_ENGINE=xtts
XTTS_SPEAKER_WAV=assets/voices/astra_ref.wav
```

Evaluate:

```bash
python scripts/eval_tts_hinglish.py --engine both --whisper-cer
```

## F5 inference parameters

| Variable | Hinglish default | Purpose |
|----------|------------------|---------|
| `F5_CFG_STRENGTH` | 2.2 | Reference adherence (lower if robotic) |
| `F5_NFE_STEPS` | 22 | Quality vs latency |
| `F5_SPEED` | 0.84 | Indian interview pace |
| `F5_DEVANAGARI_NO_SPLIT_MAX_CHARS` | 90 | Shorter chunks for Devanagari |
| `F5_CROSS_FADE_DURATION` | 0.18 | Smoother chunk joins |

## Whisper STT

`WHISPER_LANGUAGE=auto` + `data/vocab/whisper_hinglish_prompt.txt` (from export) for Hinglish recognition.

## Technical interviewer mode

`BOT_MODE=interview` uses [`streaming/prompts_interviewer.py`](streaming/prompts_interviewer.py). When `TTS_OUTPUT_SCRIPT=devanagari`, the system prompt instructs Devanagari Hindi + Latin English tech terms.

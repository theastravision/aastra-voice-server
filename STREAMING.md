# Real-time streaming voice (`/ws/voice`) — open source

Duplex pipeline: **PCM in → faster-whisper → OpenAI (stream) → Indic Parler-TTS → PCM out**.

No paid STT/TTS APIs. The only external cost is **OpenAI** for dialogue.

## Architecture

```
Browser (16 kHz PCM) → WhisperChunkSTT → GPT-4o-mini stream → Parler EN/HI captions → PCM playback
```

| Component | Engine |
|-----------|--------|
| STT | `faster-whisper` (`WHISPER_MODEL=large-v3`) |
| TTS | [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts) |
| Hinglish TTS | Script-split: Latin → `PARLER_CAPTION_EN`, Devanagari → `PARLER_CAPTION_HI` |
| LLM | OpenAI API (`gpt-4o-mini` recommended) |

**Latency:** ~2–4 s per turn on GPU after warmup (Whisper + Parler). See [docs/PARLER_TTS.md](docs/PARLER_TTS.md) for streaming optimizations.

## Quick start

```env
STT_PROVIDER=whisper_chunk
TTS_PROVIDER=parler
HF_TOKEN=hf_...
OPENAI_API_KEY=sk-...
WHISPER_MODEL=large-v3
WHISPER_LANGUAGE=auto
```

Open **`/stream`** for the demo UI, or connect to `ws://HOST:8000/ws/voice`.

## WebSocket protocol

1. JSON config:

```json
{"type":"config","stt_provider":"whisper_chunk","tts_provider":"parler","language":"hi-IN"}
```

2. Binary frames: PCM s16le, 16 kHz mono (~30 ms chunks).

3. End utterance: `{"type":"end_utterance"}`

4. Barge-in: `{"type":"barge_in"}`

Server sends JSON transcripts + **binary** PCM audio (no base64).

## Files

| Path | Role |
|------|------|
| `routers/ws_stream.py` | WebSocket endpoint |
| `streaming/orchestrator.py` | Pipeline |
| `providers/stt_whisper_chunk.py` | Chunked Whisper |
| `providers/tts_parler.py` | Streaming Parler |
| `engines/parler_tts.py` | Model load + synthesis |
| `engines/hinglish_tts.py` | Mixed-script batch TTS |

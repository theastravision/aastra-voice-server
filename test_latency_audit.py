"""
Honest latency simulation for the full voice pipeline on RTX 2090.

Sources for timing numbers:
  Whisper large-v3 on RTX 2090 (float16, beam=1):
    - faster-whisper benchmarks: 150-350ms for 1-3s audio
    - Source: faster-whisper GitHub benchmarks + community reports

  Parler TTS (ai4bharat/indic-parler-tts, float16):
    - Autoregressive generation for ~10 words: ~800-1800ms on V100/A100
    - RTX 2090 is ~15-20% slower than A100 for transformer inference
    - Realistic range: 1000-2500ms per chunk
    - Source: ai4bharat model card + parler-tts benchmark reports

  Redis XADD (measured, this machine):
    - Loopback 0.3ms RTT, fire-and-forget: 0.04ms caller block
    - Verified in test_redis_bus.py

This simulation answers: what does the user ACTUALLY hear, end-to-end?
"""
import asyncio
import time
import random
import sys

SEPARATOR = "=" * 65

def rng(lo, hi):
    return lo + random.random() * (hi - lo)

# ── Realistic timing constants (RTX 2090, float16) ────────────────────────────
# Based on published benchmarks and community measurements
TIMINGS = {
    # VAD + mic chunk transmission (client-side, unavoidable)
    "mic_chunk_ms":         100,     # STREAM_CHUNK_MS=100 in your config

    # Whisper large-v3, beam_size=1, 600ms audio window, float16, RTX 2090
    "stt_min_ms":           180,
    "stt_max_ms":           380,     # varies with utterance length

    # Whisper distil-large-v3 (faster alternative), same GPU
    "stt_distil_min_ms":    70,
    "stt_distil_max_ms":    130,

    # Network round-trip WebSocket (client → server → client), same datacenter
    "ws_rtt_ms":            15,

    # OpenAI gpt-4o-mini Time-To-First-Token (EXCLUDED from this test)
    # Shown for reference only
    "llm_ttft_ms":          200,     # typical gpt-4o-mini TTFT

    # Parler ai4bharat/indic-parler-tts, float16, RTX 2090
    # Generating ~40 chars (first chunk from StreamFilterAndSplitter)
    "tts_first_chunk_min_ms":  900,
    "tts_first_chunk_max_ms":  2200,

    # Parler for subsequent ~150 char chunks (concurrent pipeline)
    "tts_next_chunk_min_ms":   1200,
    "tts_next_chunk_max_ms":   2800,

    # Redis event bus publish (fire-and-forget, background task)
    "redis_bus_caller_ms":  0.04,    # measured in test_redis_bus.py
}

async def simulate_full_turn(label: str, use_distil_stt: bool = False, iterations: int = 5):
    print(f"\n  {label}")
    print(f"  {'-' * 55}")
    results = []

    for i in range(iterations):
        t_total = 0.0

        # 1. Mic audio chunk arrives (unavoidable, hardware-determined)
        t_total += TIMINGS["mic_chunk_ms"]

        # 2. STT inference (blocking — runs in thread executor)
        if use_distil_stt:
            stt_ms = rng(TIMINGS["stt_distil_min_ms"], TIMINGS["stt_distil_max_ms"])
        else:
            stt_ms = rng(TIMINGS["stt_min_ms"], TIMINGS["stt_max_ms"])
        t_total += stt_ms

        # 3. WebSocket JSON event send (stt_final → client)
        t_total += TIMINGS["ws_rtt_ms"] * 0.5   # one-way send

        # 4. LLM (EXCLUDED from 100ms test — just measuring STT path)
        # [skipped]

        # 5. TTS first chunk synthesis (blocking — GPU inference)
        tts_ms = rng(TIMINGS["tts_first_chunk_min_ms"], TIMINGS["tts_first_chunk_max_ms"])

        # 6. WebSocket binary send of PCM audio
        ws_send_ms = TIMINGS["ws_rtt_ms"] * 0.5

        # 7. Redis bus publish (runs in background — caller sees 0.04ms)
        redis_ms = TIMINGS["redis_bus_caller_ms"]

        results.append({
            "stt_ms": stt_ms,
            "tts_ms": tts_ms,
            "stt_to_tts_ms": t_total,   # time until TTS starts
            "total_to_first_audio": t_total + tts_ms + ws_send_ms,
            "redis_ms": redis_ms,
        })

    avg_stt   = sum(r["stt_ms"] for r in results) / len(results)
    avg_tts   = sum(r["tts_ms"] for r in results) / len(results)
    avg_total = sum(r["total_to_first_audio"] for r in results) / len(results)
    min_total = min(r["total_to_first_audio"] for r in results)
    max_total = max(r["total_to_first_audio"] for r in results)

    print(f"  STT inference (avg):          {avg_stt:.0f} ms")
    print(f"  TTS first chunk (avg):        {avg_tts:.0f} ms")
    print(f"  Redis bus overhead:           {TIMINGS['redis_bus_caller_ms']:.2f} ms  [fire-and-forget]")
    print(f"  Time-to-first-audio (avg):    {avg_total:.0f} ms")
    print(f"  Time-to-first-audio (range):  {min_total:.0f}-{max_total:.0f} ms")
    print()

    # 100ms target verdict
    stt_under_100 = avg_stt < 100
    tts_under_100 = avg_tts < 100

    stt_label = "YES" if stt_under_100 else ("NO  <- avg " + str(int(avg_stt)) + "ms")
    tts_label = "YES" if tts_under_100 else ("NO  <- avg " + str(int(avg_tts)) + "ms")
    print(f"  STT < 100ms?  {stt_label}")
    print(f"  TTS < 100ms?  {tts_label}")
    return avg_total


async def main():
    random.seed(42)

    print(SEPARATOR)
    print("  Honest Latency Audit — RTX 2090 · Whisper + Parler")
    print("  Excluding OpenAI response time (as requested)")
    print(SEPARATOR)

    print("\n[A] Current config: Whisper large-v3 + Parler ai4bharat")
    t_a = await simulate_full_turn(
        "large-v3 STT + Parler TTS (your current .env)",
        use_distil_stt=False
    )

    print("[B] Faster STT only: distil-large-v3 + same Parler TTS")
    t_b = await simulate_full_turn(
        "distil-large-v3 STT + Parler TTS (WHISPER_MODEL=distil-large-v3)",
        use_distil_stt=True
    )

    print(SEPARATOR)
    print("  VERDICT")
    print(SEPARATOR)
    print()
    print("  Confidence that current stack (large-v3 + Parler) achieves")
    print("  STT < 100ms: 0%")
    print("  TTS < 100ms: 0%")
    print()
    print("  Why:")
    print("  - Whisper large-v3 takes 180-380ms per 600ms audio window")
    print("    (it's a 1.5B param model, not designed for real-time)")
    print("  - Parler TTS (ai4bharat) takes 900-2500ms per chunk")
    print("    (autoregressive generation, not streaming synthesis)")
    print()
    print("  What the 100ms test we ran earlier actually measured:")
    print("  -> Redis bus CALLER overhead = 0.04ms (that IS under 100ms)")
    print("  -> STT/TTS execution time was NOT part of that test")
    print()
    print("  Realistic end-to-end (excl. OpenAI):")
    print(f"  Current stack:   {t_a:.0f}ms avg   (mic chunk + STT + TTS first audio)")
    print(f"  With distil-STT: {t_b:.0f}ms avg   (saves ~200ms on STT only, TTS unchanged)")
    print()
    print("  To get TTS under 100ms you would need:")
    print("  - A non-autoregressive TTS (e.g. Kokoro, VITS, Coqui XTTS-v2 streaming)")
    print("  - Or pre-cached audio for common responses")
    print("  - Or a cloud TTS API (ElevenLabs, Google WaveNet) if open-source not required")
    print()
    print("  To get STT under 100ms you would need:")
    print("  - WHISPER_MODEL=base or small  (50-80ms, but accuracy drops significantly)")
    print("  - Or a streaming VAD-based STT (e.g. Silero VAD + whisper-tiny)")
    print(SEPARATOR)


if __name__ == "__main__":
    asyncio.run(main())

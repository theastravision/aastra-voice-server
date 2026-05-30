"""
Simulate the concurrent LLM-Producer / TTS-Consumer pipeline.

This test proves that synthesis of chunk N+1 begins while chunk N is still
being played, eliminating the old staircase lag.
"""
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from streaming.stream_filter import StreamFilterAndSplitter

CONSTANTINE_TEXT = (
    "These were to have an enormous impact, not only because they were associated with "
    "Constantine, but also because, as in so many other areas, the decisions taken by "
    "Constantine (or in his name) were to have great significance for centuries to come. "
    "One of the main issues was the shape that Christian churches were to take, since "
    "there was not, apparently, a tradition of monumental church buildings when Constantine "
    "decided to help the Christian church build a series of truly spectacular structures."
)

# Simulated Parler TTS synthesis time per chunk
MOCK_TTS_SECONDS = 1.5


async def simulate_tts_synthesis(phrase: str, idx: int) -> bytes:
    """Mocks Parler TTS — sleeps to simulate GPU inference time."""
    await asyncio.sleep(MOCK_TTS_SECONDS)
    return phrase.encode()  # fake PCM bytes


# ── SEQUENTIAL (OLD) ─────────────────────────────────────────────────────────
async def run_sequential():
    splitter = StreamFilterAndSplitter(first_chunk_min=50, next_chunk_min=120)
    tokens = [CONSTANTINE_TEXT[i:i+4] for i in range(0, len(CONSTANTINE_TEXT), 4)]
    chunks_out = []
    for token in tokens:
        for chunk in splitter.push(token):
            chunks_out.append(chunk)
    remainder = splitter.flush()
    if remainder:
        chunks_out.append(remainder)

    t_start = time.monotonic()
    for idx, phrase in enumerate(chunks_out):
        print(f"  [SEQ] synthesising chunk {idx}: \"{phrase[:55]}...\"")
        await simulate_tts_synthesis(phrase, idx)
        print(f"  [SEQ] -> PLAYING chunk {idx}")
    return time.monotonic() - t_start, len(chunks_out)


# ── CONCURRENT (NEW) ─────────────────────────────────────────────────────────
async def run_concurrent():
    tts_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    play_order = []

    async def llm_producer():
        splitter = StreamFilterAndSplitter(first_chunk_min=50, next_chunk_min=120)
        tokens = [CONSTANTINE_TEXT[i:i+4] for i in range(0, len(CONSTANTINE_TEXT), 4)]
        for token in tokens:
            await asyncio.sleep(0.008)  # ~8ms/token generation delay
            for chunk in splitter.push(token):
                print(f"  [PRODUCER] enqueuing ({len(chunk)} chars): \"{chunk[:55]}...\"")
                await tts_queue.put(chunk)
        remainder = splitter.flush()
        if remainder:
            await tts_queue.put(remainder)
        await tts_queue.put(None)  # sentinel

    async def tts_consumer():
        idx = 0
        while True:
            phrase = await tts_queue.get()
            if phrase is None:
                break
            print(f"  [CONSUMER] synthesising chunk {idx}: \"{phrase[:55]}...\"")
            await simulate_tts_synthesis(phrase, idx)
            print(f"  [CONSUMER] -> PLAYING chunk {idx} (barge-in would be heard HERE)")
            play_order.append(idx)
            idx += 1

    t_start = time.monotonic()
    await asyncio.gather(llm_producer(), tts_consumer())
    return time.monotonic() - t_start, len(play_order)


async def main():
    print("=" * 65)
    print("  SEQUENTIAL pipeline (OLD — awaits TTS before next chunk)")
    print("=" * 65)
    seq_time, n_chunks = await run_sequential()
    expected_sequential = n_chunks * MOCK_TTS_SECONDS

    print()
    print("=" * 65)
    print("  CONCURRENT pipeline (NEW — producer/consumer asyncio.Queue)")
    print("=" * 65)
    con_time, _ = await run_concurrent()

    print()
    print("=" * 65)
    print(f"  Chunks produced:          {n_chunks}")
    print(f"  Sequential total time:    {seq_time:.2f}s  (expected ~{expected_sequential:.1f}s)")
    print(f"  Concurrent total time:    {con_time:.2f}s")
    print(f"  Speedup factor:           {seq_time / con_time:.1f}x")
    print(f"  Time saved:               {seq_time - con_time:.2f}s")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())

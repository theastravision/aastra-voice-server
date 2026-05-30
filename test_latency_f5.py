#!/usr/bin/env python3
"""Measure STT flush → first TTS PCM byte latency (requires GPU + models)."""

from __future__ import annotations

import asyncio
import time


async def measure_tts_ttfb() -> float | None:
    try:
        from engines.f5_tts_engine import f5_available, get_manager
    except ImportError:
        print('SKIP: f5-tts not installed')
        return None
    if not f5_available():
        print('SKIP: f5-tts not available')
        return None

    mgr = get_manager()
    start = time.perf_counter()
    for pcm, _sr in mgr.synthesize_stream_sync('Hello, this is a latency test.'):
        if pcm:
            return (time.perf_counter() - start) * 1000
    return None


async def main() -> None:
    ttfb = await measure_tts_ttfb()
    if ttfb is None:
        return
    print(f'F5-TTS first PCM chunk TTFB: {ttfb:.0f} ms')
    if ttfb < 500:
        print('PASS: under 500 ms perceptual target')
    else:
        print('WARN: above 500 ms — tune F5_NFE_STEPS or GPU')


if __name__ == '__main__':
    asyncio.run(main())

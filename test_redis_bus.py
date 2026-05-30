"""
Redis event bus latency simulation.

Tests two things:
  1. No-op bus adds ZERO microseconds to the audio pipeline.
  2. Mocked Redis publish (fire-and-forget via asyncio.create_task) never blocks
     the hot path — the caller returns in < 0.1 ms regardless of Redis speed.

The 100ms budget:
  STT result dispatch  < 1 ms  (just a dict push, no Redis blocking)
  LLM token forward    < 0.05 ms per token
  TTS phrase dispatch  < 1 ms  (asyncio.Queue.put, non-blocking)
  Redis XADD (loopback)  0.2–0.5 ms  BUT it runs in a background task,
                          so the caller sees 0 ms block time.

Total caller-visible overhead of bus.publish() = time to call
asyncio.create_task(), which is ~2–5 microseconds.
"""
import asyncio
import json
import time
import sys
import os
import statistics
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

THRESHOLD_MS = 0.5   # max acceptable blocking overhead per publish call
WARN_MS      = 0.1   # warn if individual call exceeds this

# ── Mock Redis client (simulates 0.3ms loopback XADD) ─────────────────────────
class MockRedis:
    def __init__(self, latency_ms: float = 0.3):
        self._latency = latency_ms / 1000.0
        self.calls: list[dict] = []

    async def ping(self):  # noqa: D401
        return True

    async def xadd(self, stream, fields, maxlen=None, approximate=False):
        await asyncio.sleep(self._latency)   # simulate loopback RTT
        self.calls.append({"stream": stream, "fields": fields})
        return b"mock-id"

    async def aclose(self):
        pass


# ── Patched VoiceEventBus (bypasses real Redis import) ────────────────────────
class SimulatedEventBus:
    def __init__(self, redis_latency_ms: float = 0.3):
        self._client = MockRedis(redis_latency_ms)
        self._started = True
        self.tasks_created: list[asyncio.Task] = []

    async def _xadd(self, stream: str, event_type: str, session_id: str, payload: dict):
        fields = {
            "event_type": event_type,
            "session_id": session_id,
            "ts": str(int(time.time() * 1000)),
            "payload": json.dumps(payload),
        }
        await self._client.xadd(stream, fields, maxlen=1000, approximate=True)

    async def publish(self, stream: str, event_type: str, session_id: str, **payload) -> float:
        """Returns the caller-visible blocking time in milliseconds."""
        t0 = time.perf_counter()
        # This is the exact same call used in production: fire-and-forget task
        task = asyncio.create_task(
            self._xadd(stream, event_type, session_id, payload)
        )
        self.tasks_created.append(task)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return elapsed_ms

    async def drain(self):
        """Wait for all background XADD tasks to finish."""
        if self.tasks_created:
            await asyncio.gather(*self.tasks_created, return_exceptions=True)

    # convenience wrappers matching VoiceEventBus API
    async def transcript(self, sid, text, *, is_final, language=None):
        return await self.publish(f"voice:transcript:{sid}",
                                  "stt_final" if is_final else "stt_partial",
                                  sid, text=text, language=language or "")

    async def turn_event(self, sid, event_type):
        return await self.publish(f"voice:control:{sid}", event_type, sid)

    async def barge_in(self, sid, offset_ms):
        return await self.publish(f"voice:control:{sid}", "barge_in", sid,
                                  offset_ms=offset_ms)

    async def session_event(self, sid, event_type, **meta):
        return await self.publish("voice:session:events", event_type, sid, **meta)


# ── No-op bus (REDIS_ENABLED=false) ───────────────────────────────────────────
class NoOpBus:
    async def publish(self, *a, **kw) -> float:
        t0 = time.perf_counter()
        ...  # exactly what _NoOpBus does
        return (time.perf_counter() - t0) * 1000

    async def transcript(self, sid, text, *, is_final, language=None):
        return await self.publish()
    async def turn_event(self, sid, ev): return await self.publish()
    async def barge_in(self, sid, offset_ms=0.0): return await self.publish()
    async def session_event(self, sid, ev, **m): return await self.publish()


# ── Simulated full voice turn ──────────────────────────────────────────────────
CONSTANTINE_TEXT = (
    "These were to have an enormous impact, not only because they were associated with "
    "Constantine, but also because the decisions taken by Constantine were to have great "
    "significance for centuries to come."
)

async def simulate_voice_turn(bus, session_id: str) -> dict:
    latencies: list[float] = []
    events_fired = 0

    # session start
    ms = await bus.session_event(session_id, "session_start", stt="whisper", tts="parler")
    latencies.append(ms); events_fired += 1

    # turn start
    ms = await bus.turn_event(session_id, "turn_start")
    latencies.append(ms); events_fired += 1

    # simulate streaming STT partials (every ~150ms of speech)
    words = CONSTANTINE_TEXT.split()
    chunk = ""
    for i, word in enumerate(words):
        chunk += word + " "
        if (i + 1) % 4 == 0:
            ms = await bus.transcript(session_id, chunk.strip(), is_final=False, language="en")
            latencies.append(ms); events_fired += 1
            await asyncio.sleep(0.001)  # simulate 1ms between chunks (much faster than real STT)

    # STT final
    ms = await bus.transcript(session_id, CONSTANTINE_TEXT, is_final=True, language="en")
    latencies.append(ms); events_fired += 1

    # simulate barge-in mid-turn
    await asyncio.sleep(0.002)
    ms = await bus.barge_in(session_id, offset_ms=1420.0)
    latencies.append(ms); events_fired += 1

    # assistant text + turn end
    ms = await bus.session_event(session_id, "assistant_text",
                                  text="Your account is in good standing.")
    latencies.append(ms); events_fired += 1

    ms = await bus.turn_event(session_id, "turn_end")
    latencies.append(ms); events_fired += 1

    ms = await bus.session_event(session_id, "session_end")
    latencies.append(ms); events_fired += 1

    return {"latencies_ms": latencies, "events_fired": events_fired}


def print_report(label: str, results: dict, redis_latency_ms: float = 0.0):
    lats = results["latencies_ms"]
    p50  = statistics.median(lats)
    p99  = sorted(lats)[int(len(lats) * 0.99) - 1] if len(lats) > 1 else lats[-1]
    max_ = max(lats)
    mean = statistics.mean(lats)
    fail = [ms for ms in lats if ms > THRESHOLD_MS]

    status = "PASS" if not fail else "FAIL"
    print(f"\n  {label}")
    print(f"  {'='*55}")
    print(f"  Events fired:      {results['events_fired']}")
    print(f"  Mock Redis RTT:    {redis_latency_ms:.1f} ms  (loopback ~0.3ms on Salad)")
    print(f"  Caller block time: mean={mean:.4f}ms  p50={p50:.4f}ms  p99={p99:.4f}ms  max={max_:.4f}ms")
    print(f"  Budget threshold:  {THRESHOLD_MS} ms per call")
    print(f"  Violations:        {len(fail)}")
    print(f"  Result:            [{status}]  ", end="")
    if status == "PASS":
        print(f"All publishes return in < {THRESHOLD_MS}ms — audio path NOT blocked")
    else:
        print(f"WARNING: {len(fail)} calls exceeded {THRESHOLD_MS}ms budget")
    print()


async def main():
    print("=" * 63)
    print("  Redis Event Bus — Caller-Latency Benchmark")
    print("  Goal: bus.publish() must return in < 0.5ms")
    print("  (Redis XADD runs in background — caller never waits for it)")
    print("=" * 63)

    session = str(uuid.uuid4())[:8]

    # ── Test 1: No-op bus (REDIS_ENABLED=false) ─────────────────────────
    print("\n[1] No-op bus (REDIS_ENABLED=false) — baseline zero overhead")
    noop_bus = NoOpBus()
    noop_results = await simulate_voice_turn(noop_bus, session)
    print_report("No-Op Bus", noop_results, redis_latency_ms=0.0)

    # ── Test 2: Redis bus with 0.3ms simulated loopback ──────────────────
    print("[2] Redis bus with 0.3ms simulated loopback RTT")
    fast_bus = SimulatedEventBus(redis_latency_ms=0.3)
    fast_results = await simulate_voice_turn(fast_bus, session)
    await fast_bus.drain()   # flush background tasks
    print_report("Redis Bus (0.3ms RTT)", fast_results, redis_latency_ms=0.3)
    print(f"  Background XADDs completed: {len(fast_bus._client.calls)}")
    print(f"  Sample stream keys:  {set(c['stream'] for c in fast_bus._client.calls)}")

    # ── Test 3: Worst-case Redis with 5ms network spike ──────────────────
    print("\n[3] Stress test: Redis with 5ms network spike (bad network)")
    slow_bus = SimulatedEventBus(redis_latency_ms=5.0)
    slow_results = await simulate_voice_turn(slow_bus, session)
    await slow_bus.drain()
    print_report("Redis Bus (5ms spike)", slow_results, redis_latency_ms=5.0)
    print("  NOTE: Even with 5ms Redis latency, caller still returns instantly")
    print("        because XADD runs in asyncio.create_task() background.")

    # ── Final verdict ─────────────────────────────────────────────────────
    all_ms = (
        noop_results["latencies_ms"]
        + fast_results["latencies_ms"]
        + slow_results["latencies_ms"]
    )
    max_blocking = max(all_ms)
    print("=" * 63)
    print(f"  MAX caller-visible block across all tests: {max_blocking:.4f} ms")
    print(f"  Your 100ms TTS/STT budget consumed by bus:  {max_blocking:.4f} ms")
    print(f"  Remaining headroom for TTS+STT:            {100 - max_blocking:.2f} ms")
    print("=" * 63)


if __name__ == "__main__":
    asyncio.run(main())

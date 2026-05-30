"""
Async Redis Streams event bus for the voice pipeline.

Design goals:
  - When REDIS_ENABLED=False (default), every method is a no-op — the pipeline
    runs exactly as before and redis is never imported.
  - All publishes are fire-and-forget (asyncio.create_task) so they never block
    the real-time audio hot path.
  - Each stream uses MAXLEN ~REDIS_MAX_STREAM_LEN (approximate trim, O(1)) to
    bound memory usage automatically.
  - Every message has a typed envelope:
      event_type  : str
      session_id  : str
      ts          : unix milliseconds
      payload     : JSON-encoded dict of event-specific fields

Stream Key Schema
─────────────────
  voice:transcript:{session_id}   STT partial + final results
  voice:control:{session_id}      barge_in, turn_start, turn_end per session
  voice:session:events            all session lifecycle events (global)

Usage
─────
  from streaming.event_bus import get_event_bus
  bus = get_event_bus()
  await bus.transcript(session_id, text, is_final=True, language='en')
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from config import (
    REDIS_ENABLED,
    REDIS_MAX_STREAM_LEN,
    REDIS_URL,
)

logger = logging.getLogger(__name__)

_SESSION_EVENTS_KEY = "voice:session:events"


class _NoOpBus:
    """Silent no-op bus used when REDIS_ENABLED=False."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def publish(self, stream: str, event_type: str, session_id: str, **payload: Any) -> None: ...  # noqa: E501

    async def transcript(self, session_id: str, text: str, *, is_final: bool, language: str | None = None) -> None: ...  # noqa: E501
    async def turn_event(self, session_id: str, event_type: str) -> None: ...
    async def barge_in(self, session_id: str, offset_ms: float) -> None: ...
    async def audio_ready(self, session_id: str, sample_rate: int) -> None: ...
    async def session_event(self, session_id: str, event_type: str, **meta: Any) -> None: ...


class VoiceEventBus:
    """Redis Streams publisher for voice pipeline events."""

    def __init__(self) -> None:
        self._client: Any = None  # redis.asyncio.Redis
        self._started = False

    async def start(self) -> None:
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            self._client = aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=1,
            )
            # Verify connection
            await self._client.ping()  # type: ignore[misc]  # redis-py stubs mark ping() as bool, but redis.asyncio makes it a coroutine
            self._started = True
            logger.info("VoiceEventBus connected to Redis at %s", REDIS_URL)
        except Exception as exc:
            logger.warning(
                "VoiceEventBus: Redis unavailable (%s) — continuing without pub/sub", exc
            )
            self._client = None
            self._started = False

    async def stop(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        self._started = False
        logger.info("VoiceEventBus stopped")

    # ── Core publish ─────────────────────────────────────────────────────────

    async def publish(self, stream: str, event_type: str, session_id: str, **payload: Any) -> None:
        """Fire-and-forget publish. Never raises — logs on failure."""
        if not self._client:
            return
        asyncio.create_task(self._xadd(stream, event_type, session_id, payload))

    async def _xadd(self, stream: str, event_type: str, session_id: str, payload: dict) -> None:
        try:
            fields = {
                "event_type": event_type,
                "session_id": session_id,
                "ts": str(int(time.time() * 1000)),
                "payload": json.dumps(payload, ensure_ascii=False),
            }
            await self._client.xadd(
                stream,
                fields,
                maxlen=REDIS_MAX_STREAM_LEN,
                approximate=True,  # O(1) trimming
            )
        except Exception as exc:
            logger.debug("VoiceEventBus xadd failed (%s) — non-fatal", exc)

    # ── Typed convenience methods ─────────────────────────────────────────────

    async def transcript(
        self,
        session_id: str,
        text: str,
        *,
        is_final: bool,
        language: str | None = None,
    ) -> None:
        stream = f"voice:transcript:{session_id}"
        await self.publish(
            stream,
            "stt_final" if is_final else "stt_partial",
            session_id,
            text=text,
            language=language or "",
        )

    async def turn_event(self, session_id: str, event_type: str) -> None:
        stream = f"voice:control:{session_id}"
        await self.publish(stream, event_type, session_id)

    async def barge_in(self, session_id: str, offset_ms: float) -> None:
        stream = f"voice:control:{session_id}"
        await self.publish(stream, "barge_in", session_id, offset_ms=offset_ms)

    async def audio_ready(self, session_id: str, sample_rate: int) -> None:
        stream = f"voice:audio_ready:{session_id}"
        await self.publish(stream, "audio_chunk_sent", session_id, sample_rate=sample_rate)

    async def session_event(self, session_id: str, event_type: str, **meta: Any) -> None:
        await self.publish(_SESSION_EVENTS_KEY, event_type, session_id, **meta)


# ── Singleton factory ─────────────────────────────────────────────────────────

_bus: VoiceEventBus | _NoOpBus | None = None


def get_event_bus() -> VoiceEventBus | _NoOpBus:
    global _bus
    if _bus is None:
        _bus = VoiceEventBus() if REDIS_ENABLED else _NoOpBus()
        if not REDIS_ENABLED:
            logger.info("VoiceEventBus: REDIS_ENABLED=false — running in no-op mode")
    return _bus

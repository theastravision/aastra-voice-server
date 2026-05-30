"""Duplex audio buffer — prevents races between user mic and agent playback."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class DuplexAudioState:
    """Thread-safe duplex state for one voice WebSocket session."""

    sample_rate: int = 16000
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    incoming_pcm: deque[bytes] = field(default_factory=deque)
    incoming_bytes: int = 0
    max_incoming_bytes: int = 16000 * 2 * 30  # ~30 s at 16 kHz mono s16

    agent_speaking: bool = False
    barge_in_requested: bool = False
    user_speaking: bool = False
    last_user_audio_at: float = 0.0

    turn_in_progress: bool = False
    cancel_generation: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.cancel_generation.set()

    async def push_incoming(self, chunk: bytes) -> None:
        if not chunk:
            return
        async with self.lock:
            self.incoming_pcm.append(chunk)
            self.incoming_bytes += len(chunk)
            self.last_user_audio_at = time.monotonic()
            while self.incoming_bytes > self.max_incoming_bytes and self.incoming_pcm:
                dropped = self.incoming_pcm.popleft()
                self.incoming_bytes -= len(dropped)

    async def drain_incoming(self, max_bytes: int | None = None) -> bytes:
        async with self.lock:
            if not self.incoming_pcm:
                return b''
            if max_bytes is None:
                parts = list(self.incoming_pcm)
                self.incoming_pcm.clear()
                self.incoming_bytes = 0
                return b''.join(parts)
            out = bytearray()
            while self.incoming_pcm and len(out) < max_bytes:
                part = self.incoming_pcm.popleft()
                need = max_bytes - len(out)
                if len(part) <= need:
                    out.extend(part)
                    self.incoming_bytes -= len(part)
                else:
                    out.extend(part[:need])
                    self.incoming_pcm.appendleft(part[need:])
                    self.incoming_bytes -= need
                    break
            return bytes(out)

    async def set_agent_speaking(self, speaking: bool) -> None:
        async with self.lock:
            self.agent_speaking = speaking
            if not speaking:
                self.barge_in_requested = False

    async def request_barge_in(self) -> None:
        async with self.lock:
            self.barge_in_requested = True
            self.agent_speaking = False
        self.cancel_generation.set()

    async def begin_turn(self) -> None:
        async with self.lock:
            self.turn_in_progress = True
        self.cancel_generation.clear()

    async def end_turn(self) -> None:
        async with self.lock:
            self.turn_in_progress = False
        self.cancel_generation.set()

    async def should_barge_in(self, energy: float, threshold: float = 0.04) -> bool:
        async with self.lock:
            if not self.agent_speaking:
                return False
            if energy > threshold:
                self.barge_in_requested = True
                return True
            return self.barge_in_requested

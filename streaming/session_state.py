"""Session phase state machine with asyncio mutex for voice pipeline turns."""

from __future__ import annotations

import asyncio
from enum import Enum


class SessionPhase(Enum):
    IDLE = 'idle'
    GREETING = 'greeting'
    LISTENING = 'listening'
    STT_PROCESSING = 'stt_processing'
    LLM_STREAMING = 'llm_streaming'
    TTS_PLAYING = 'tts_playing'


# Phases where incoming PCM must not trigger STT or re-enter the pipeline.
_LOCKED_PHASES = frozenset(
    {
        SessionPhase.GREETING,
        SessionPhase.STT_PROCESSING,
        SessionPhase.LLM_STREAMING,
        SessionPhase.TTS_PLAYING,
    }
)


class SessionStateMachine:
    """Strict session mutex — one active turn at a time; greeting runs once."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.phase = SessionPhase.IDLE
        self.is_greeted = False

    async def try_greet(self) -> bool:
        """Return True only on the first greeting attempt for this session."""
        async with self.lock:
            if self.is_greeted:
                return False
            if self.phase in _LOCKED_PHASES:
                return False
            self.is_greeted = True
            self.phase = SessionPhase.GREETING
            return True

    async def accept_pcm_for_stt(self) -> bool:
        """False while agent is busy — PCM may still feed barge-in energy checks."""
        async with self.lock:
            return self.phase == SessionPhase.LISTENING

    async def is_locked(self) -> bool:
        async with self.lock:
            return self.phase in _LOCKED_PHASES

    async def transition(self, to: SessionPhase) -> None:
        async with self.lock:
            self.phase = to

    async def begin_listening(self) -> None:
        """Turn finished — unlock mic/STT intake."""
        async with self.lock:
            self.phase = SessionPhase.LISTENING

    @property
    def processing(self) -> bool:
        """Sync snapshot — prefer is_locked() in async code."""
        return self.phase in _LOCKED_PHASES

"""F5-TTS / XTTS streaming worker with Hinglish engine routing."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from engines.interjections import CachedInterjection
from engines.tts_router import resolve_tts_backend
from providers.base import TtsAudioChunk

logger = logging.getLogger(__name__)


class TtsWorker:
    """Async wrapper around F5-TTS or XTTS streaming inference."""

    def __init__(self) -> None:
        self._language_hint: str | None = None
        self._reply_script: str = 'en'
        self._voice_id: str | None = None
        self._backend: str = 'f5'

    async def start(
        self,
        *,
        language_hint: str | None = None,
        voice_id: str | None = None,
    ) -> None:
        self._language_hint = language_hint
        self._voice_id = voice_id
        hint = (language_hint or 'en').lower()
        if hint in ('hi', 'hinglish'):
            self._reply_script = hint
        elif hint in ('en', 'english', 'en-in'):
            self._reply_script = 'en'
        else:
            self._reply_script = hint if hint in ('hi', 'hinglish') else 'en'
        self._backend = resolve_tts_backend(self._reply_script)

        if self._backend == 'f5':
            from engines.f5_tts_engine import get_manager

            mgr = get_manager()
            mgr.set_active_voice(voice_id)
            mgr.reset_stream_state()
        elif self._backend == 'melotts':
            from engines.melo_tts_engine import get_manager as get_melo

            mgr = get_melo()
            mgr.set_active_voice(voice_id)
        else:
            from engines.xtts_engine import get_manager as get_xtts

            mgr = get_xtts()
            mgr.set_active_voice(voice_id)

    async def close(self) -> None:
        pass

    def synthesize_stream(self, text: str) -> AsyncIterator[TtsAudioChunk]:
        return self._stream(text)

    async def _stream(self, text: str) -> AsyncIterator[TtsAudioChunk]:
        cleaned = (text or '').strip()
        if not cleaned:
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[TtsAudioChunk | BaseException | None] = asyncio.Queue(maxsize=64)
        reply_script = self._reply_script
        backend = self._backend
        voice_id = self._voice_id

        def _producer() -> None:
            try:
                if backend == 'xtts':
                    from engines.xtts_engine import get_manager as get_xtts

                    mgr = get_xtts()
                    mgr.set_active_voice(voice_id)
                    stream = mgr.synthesize_stream_sync(cleaned, reply_script=reply_script)
                elif backend == 'melotts':
                    from engines.melo_tts_engine import get_manager as get_melo

                    mgr = get_melo()
                    mgr.set_active_voice(voice_id)
                    stream = mgr.synthesize_stream_sync(cleaned, reply_script=reply_script)
                else:
                    from engines.f5_tts_engine import get_manager

                    mgr = get_manager()
                    mgr.set_active_voice(voice_id)
                    stream = mgr.synthesize_stream_sync(cleaned, reply_script=reply_script)

                for pcm, sr in stream:
                    if pcm:
                        chunk = TtsAudioChunk(pcm_s16le=pcm, sample_rate=sr)
                        fut = asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
                        fut.result(timeout=120)
            except BaseException as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop.run_in_executor(None, _producer)

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                logger.exception('TTS synthesis failed backend=%s', backend)
                raise item
            yield item

    async def stream_cached(self, clip: CachedInterjection) -> AsyncIterator[TtsAudioChunk]:
        if clip.pcm_s16le:
            yield TtsAudioChunk(pcm_s16le=clip.pcm_s16le, sample_rate=clip.sample_rate)

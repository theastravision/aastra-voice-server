"""Full-duplex voice orchestrator: STT → LLM stream → TTS stream."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from config import (
    BOT_MODE,
    OPENAI_MODEL,
    OPENAI_VOICE_TEMPERATURE,
    STREAM_LISTEN_IDLE_SECS,
    STREAM_LLM_MIN_WORDS,
    STREAM_STT_MIN_CHARS,
)
from engines.stt_filters import (
    is_repeat_intent,
    is_substantive_utterance,
    listen_idle_message,
    repeat_last_question_message,
)
from engines.lang_detect import (
    empty_utterance_message,
    pick_reply_script_for_session,
    pick_tts_route_for_session,
    resolve_session_language,
)
from engines.llm_script_contract import should_strict_script_gate
from engines.llm_turn import build_extra_system, finalize_assistant_for_tts
from engines.tts_utils import ensure_pcm_s16le_bytes, is_speakable_text
from providers.registry import auto_stt_provider, auto_tts_provider, create_stt, create_tts
from streaming.audio_buffer import DuplexAudioState
from streaming.event_bus import VoiceEventBus, _NoOpBus, get_event_bus
from streaming.llm_stream import stream_chat_tokens
from streaming.prompts import build_messages
from streaming.stream_filter import StreamFilterAndSplitter

logger = logging.getLogger(__name__)

SendJson = Callable[[str], Awaitable[None]]
SendBinary = Callable[[bytes], Awaitable[None]]

_WORD_SPLIT = re.compile(r'(\s+)')


class VoiceStreamOrchestrator:
    def __init__(
        self,
        *,
        send_json: SendJson,
        send_binary: SendBinary,
        duplex: DuplexAudioState,
        stt_provider: str | None = None,
        tts_provider: str | None = None,
        language_hint: str | None = None,
        candidate_name: str | None = None,
        event_bus: VoiceEventBus | _NoOpBus | None = None,
    ) -> None:
        self._send_json = send_json
        self._send_binary = send_binary
        self._duplex = duplex
        self._stt_name = stt_provider or auto_stt_provider()
        self._tts_name = tts_provider or auto_tts_provider()
        self._language_hint = language_hint
        self._session_lang = resolve_session_language(language_hint)
        self._candidate_name = (candidate_name or '').strip() or None
        self._stt = create_stt(self._stt_name)
        self._tts = create_tts(self._tts_name)
        self._history: list[dict[str, str]] = []
        self._utterance_buffer = ''
        self._pending_final: str | None = None
        self._last_detected_lang: str | None = None
        self._last_stt_text = ''
        self._processing = False
        self._last_empty_prompt_at = 0.0
        self._last_idle_nudge_at = 0.0
        self._idle_task: asyncio.Task | None = None
        self.session_id = str(uuid.uuid4())
        self._barge_in_offset_ms = 0.0
        self._bus = event_bus if event_bus is not None else get_event_bus()

    async def start(self) -> None:
        await self._stt.start(language_hint=self._language_hint)
        tts_hint = self._session_lang or self._language_hint
        await self._tts.start(language_hint=tts_hint)
        await self._bus.session_event(
            self.session_id, 'session_start',
            stt=self._stt_name, tts=self._tts_name,
            language=self._language_hint or 'auto',
        )

    async def close(self) -> None:
        self._cancel_listen_idle()
        await self._stt.close()
        await self._tts.close()
        await self._bus.session_event(self.session_id, 'session_end')

    async def play_greeting(self) -> None:
        """Stream opening interview greeting over WS (no LLM)."""
        if self._processing:
            return
        self._cancel_listen_idle()
        from engines.demo_bot import _greeting_text

        name = self._candidate_name or 'Candidate'
        text, script = _greeting_text(name, self._session_lang)
        if BOT_MODE != 'interview':
            text = text if text else f'Hello {name}, welcome.'
        self._processing = True
        await self._duplex.begin_turn()
        await self._send_json(_evt('turn_start'))
        try:
            tts_route = pick_tts_route_for_session(self._session_lang, script)
            await self._tts.start(language_hint=tts_route)
            await self._send_json(_evt('assistant_delta', text=text))
            await self._stream_tts_phrase(text, tts_route)
            self._history.append({'role': 'assistant', 'content': text})
            await self._send_json(_evt('assistant_text', text=text))
        except Exception as exc:
            logger.exception('greeting failed')
            await self._send_json(_evt('error', message=str(exc)))
        finally:
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            self._processing = False
            self._schedule_listen_idle()

    async def handle_barge_in(self, offset_ms: float) -> None:
        self._barge_in_offset_ms = offset_ms
        await self._bus.barge_in(self.session_id, offset_ms)

    async def on_pcm_chunk(self, chunk: bytes, *, rms_energy: float = 0.0) -> None:
        if rms_energy > 0.02:
            self._cancel_listen_idle()
        await self._duplex.push_incoming(chunk)
        if await self._duplex.should_barge_in(rms_energy):
            await self._duplex.request_barge_in()
            await self._send_json(
                '{"type":"barge_in","message":"User interrupted agent"}'
            )

        events = await self._stt.push_pcm(chunk)
        for ev in events:
            if (ev.text or '').strip():
                self._last_stt_text = ev.text.strip()
            if ev.is_final:
                self._pending_final = ev.text
                if ev.language:
                    self._last_detected_lang = ev.language
                await self._send_json(
                    _evt('stt_final', text=ev.text, language=ev.language)
                )
                # Publish to Redis Streams (fire-and-forget)
                await self._bus.transcript(
                    self.session_id, ev.text or '',
                    is_final=True, language=ev.language,
                )
            else:
                await self._send_json(
                    _evt('stt_partial', text=ev.text, language=ev.language)
                )
                await self._bus.transcript(
                    self.session_id, ev.text or '',
                    is_final=False, language=ev.language,
                )

    async def on_end_utterance(self) -> None:
        self._cancel_listen_idle()
        async with self._duplex.lock:
            if self._duplex.agent_speaking:
                await self._duplex.request_barge_in()
                return
        if self._processing:
            await self._duplex.request_barge_in()
            await asyncio.sleep(0.05)

        await self._send_json(_evt('stt_processing'))
        events = await self._stt.flush()
        text = (self._pending_final or '').strip()
        for ev in events:
            if ev.is_final and (ev.text or '').strip():
                text = ev.text.strip()
                if ev.language:
                    self._last_detected_lang = ev.language
        if not text:
            text = self._last_stt_text.strip()
        self._pending_final = None

        if not text or not is_substantive_utterance(
            text, min_chars=STREAM_STT_MIN_CHARS
        ):
            await self._prompt_empty_utterance()
            return
        self._last_stt_text = ''
        if is_repeat_intent(text):
            asyncio.create_task(self._repeat_last_question())
            return
        asyncio.create_task(self._run_turn(text))

    async def _run_turn(self, user_text: str) -> None:
        self._processing = True
        self._barge_in_offset_ms = 0.0
        await self._duplex.begin_turn()
        await self._send_json(_evt('turn_start'))
        await self._bus.turn_event(self.session_id, 'turn_start')
        try:
            reply_script = pick_reply_script_for_session(
                self._session_lang, self._last_detected_lang, user_text
            )
            messages = build_messages(
                history=self._history[-16:],
                user_text=user_text,
                extra_system=build_extra_system(self._session_lang, reply_script),
                candidate_name=self._candidate_name,
            )
            self._history.append({'role': 'user', 'content': user_text})

            tts_route = pick_tts_route_for_session(self._session_lang, reply_script)
            await self._tts.start(language_hint=tts_route)

            full_reply: list[str] = []
            strict_gate = should_strict_script_gate() and self._session_lang in (
                'hi',
                'hinglish',
            )
            finalized_text: list[str] = []

            tts_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=4)

            async def _llm_producer() -> None:
                splitter = StreamFilterAndSplitter()
                try:
                    async for token in stream_chat_tokens(
                        messages, temperature=OPENAI_VOICE_TEMPERATURE
                    ):
                        if self._duplex.cancel_generation.is_set():
                            break
                        full_reply.append(token)
                        await self._send_json(_evt('assistant_delta', text=token))
                        if not strict_gate:
                            for chunk in splitter.push(token):
                                if self._duplex.cancel_generation.is_set():
                                    break
                                await tts_queue.put(chunk)
                    if strict_gate and not self._duplex.cancel_generation.is_set():
                        raw = ''.join(full_reply).strip()
                        text, phrases = await finalize_assistant_for_tts(
                            messages,
                            raw,
                            self._session_lang,
                            reply_script,
                        )
                        finalized_text.append(text)
                        for phrase in phrases:
                            await tts_queue.put(phrase)
                    elif not strict_gate:
                        remainder = splitter.flush()
                        if remainder and not self._duplex.cancel_generation.is_set():
                            await tts_queue.put(remainder)
                finally:
                    await tts_queue.put(None)

            async def _tts_consumer() -> None:
                while True:
                    phrase = await tts_queue.get()
                    if phrase is None:
                        break  # sentinel received, done
                    if self._duplex.cancel_generation.is_set():
                        # drain remaining items quickly so producer can unblock
                        while not tts_queue.empty():
                            tts_queue.get_nowait()
                        break
                    await self._stream_tts_phrase(phrase, tts_route)

            # Run both coroutines concurrently and wait for both to finish
            await asyncio.gather(_llm_producer(), _tts_consumer())

            assistant_text = (
                finalized_text[0]
                if finalized_text
                else ''.join(full_reply).strip()
            )

            # Latency-aware truncation based on timestamped barge-in offset
            if self._duplex.cancel_generation.is_set() and self._barge_in_offset_ms > 0:
                chars_spoken = int((self._barge_in_offset_ms / 1000.0) * 15)
                if chars_spoken < len(assistant_text):
                    truncated = assistant_text[:chars_spoken]
                    last_space = truncated.rfind(' ')
                    assistant_text = truncated[:last_space] if last_space > 0 else truncated

            if assistant_text:
                self._history.append({'role': 'assistant', 'content': assistant_text})
                await self._send_json(_evt('assistant_text', text=assistant_text))
                await self._bus.session_event(
                    self.session_id, 'assistant_text', text=assistant_text
                )
        except Exception as exc:
            logger.exception('turn failed model=%s', OPENAI_MODEL)
            await self._send_json(_evt('error', message=str(exc)))
            await self._bus.session_event(self.session_id, 'turn_error', error=str(exc))
        finally:
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            await self._bus.turn_event(self.session_id, 'turn_end')
            self._processing = False
            self._schedule_listen_idle()

    async def _repeat_last_question(self) -> None:
        last_assistant = ''
        for msg in reversed(self._history):
            if msg.get('role') == 'assistant':
                last_assistant = (msg.get('content') or '').strip()
                break
        if not last_assistant:
            await self._prompt_empty_utterance()
            return

        self._processing = True
        await self._duplex.begin_turn()
        await self._send_json(_evt('turn_start'))
        try:
            ack, script = repeat_last_question_message(self._session_lang)
            tts_route = pick_tts_route_for_session(self._session_lang, script)
            await self._tts.start(language_hint=tts_route)
            await self._send_json(_evt('assistant_delta', text=ack))
            await self._stream_tts_phrase(ack, tts_route)
            await self._send_json(_evt('assistant_delta', text=last_assistant))
            await self._stream_tts_phrase(last_assistant, tts_route)
            await self._send_json(_evt('assistant_text', text=f'{ack} {last_assistant}'))
        except Exception as exc:
            logger.exception('repeat question failed')
            await self._send_json(_evt('error', message=str(exc)))
        finally:
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            self._processing = False
            self._schedule_listen_idle()

    async def _prompt_empty_utterance(self) -> None:
        now = time.monotonic()
        if now - self._last_empty_prompt_at < 8.0:
            await self._send_json(
                _evt(
                    'assistant_text',
                    text='I am still listening. Please continue when you are ready.',
                )
            )
            self._schedule_listen_idle()
            return
        self._last_empty_prompt_at = now
        logger.debug('empty utterance (no STT text)')
        hint, script = empty_utterance_message(self._session_lang)
        await self._send_json(_evt('assistant_text', text=hint))
        tts_route = pick_tts_route_for_session(self._session_lang, script)
        try:
            await self._stream_tts_phrase(hint, tts_route)
        except Exception:
            logger.exception('empty utterance TTS failed')
        finally:
            self._schedule_listen_idle()

    def _cancel_listen_idle(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    def _schedule_listen_idle(self) -> None:
        self._cancel_listen_idle()
        if STREAM_LISTEN_IDLE_SECS <= 0:
            return
        self._idle_task = asyncio.create_task(self._listen_idle_wait())

    async def _listen_idle_wait(self) -> None:
        try:
            await asyncio.sleep(STREAM_LISTEN_IDLE_SECS)
            if self._processing:
                return
            async with self._duplex.lock:
                if self._duplex.agent_speaking or self._duplex.turn_in_progress:
                    return
            now = time.monotonic()
            if now - self._last_idle_nudge_at < 15.0:
                return
            self._last_idle_nudge_at = now
            await self._speak_listen_idle_nudge()
        except asyncio.CancelledError:
            pass

    async def _speak_listen_idle_nudge(self) -> None:
        hint, script = listen_idle_message(self._session_lang)
        self._processing = True
        await self._duplex.begin_turn()
        await self._send_json(_evt('turn_start'))
        try:
            tts_route = pick_tts_route_for_session(self._session_lang, script)
            await self._tts.start(language_hint=tts_route)
            await self._send_json(_evt('assistant_text', text=hint))
            await self._stream_tts_phrase(hint, tts_route)
        except Exception:
            logger.exception('listen idle nudge failed')
        finally:
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            self._processing = False
            self._schedule_listen_idle()

    async def _stream_tts_phrase(self, phrase: str, tts_lang: str) -> None:
        if self._duplex.cancel_generation.is_set():
            return
        cleaned = (phrase or '').strip()
        if not cleaned or not is_speakable_text(cleaned):
            return
        await self._duplex.set_agent_speaking(True)
        try:
            async for chunk in self._tts.synthesize_stream(cleaned):
                if self._duplex.cancel_generation.is_set():
                    break
                sr = chunk.sample_rate or 24000
                pcm = ensure_pcm_s16le_bytes(chunk.pcm_s16le)
                if not pcm:
                    logger.warning(
                        'TTS chunk skipped: expected bytes, got %s',
                        type(chunk.pcm_s16le).__name__,
                    )
                    continue
                await self._send_json(
                    _evt('audio_config', sample_rate=sr, format='pcm_s16le')
                )
                await self._send_binary(pcm)
        except Exception as exc:
            logger.exception('TTS phrase failed')
            await self._send_json(_evt('error', message=f'TTS failed: {exc}'))
        finally:
            await self._duplex.set_agent_speaking(False)


def _evt(event_type: str, **fields) -> str:
    import json

    payload = {'type': event_type, **fields}
    return json.dumps(payload, ensure_ascii=False)

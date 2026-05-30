"""WebSocket interview session — STT → LLM → TTS pipeline with asyncio queues."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from config import (
    BOT_MODE,
    INTERJECTION_TIMEOUT_MS,
    OPENAI_MODEL,
    OPENAI_VOICE_TEMPERATURE,
    STREAM_LISTEN_IDLE_SECS,
    STREAM_STT_MIN_CHARS,
)
from engines.interjections import pick_interjection
from engines.lang_detect import (
    empty_utterance_message,
    pick_reply_script_for_session,
    pick_tts_route_for_session,
    resolve_session_language,
)
from engines.llm_script_contract import should_strict_script_gate
from engines.llm_turn import build_extra_system, finalize_assistant_for_tts
from engines.interview_guard import (
    is_off_topic_interview_question,
    off_topic_refusal_message,
)
from engines.interview_opening import (
    INTRO_FOLLOW_UP_HINT,
    InterviewPhase,
    extract_candidate_name,
    initial_interview_phase,
    interview_opening_enabled,
    name_retry_script,
    opening_script,
    welcome_and_intro_script,
)
from engines.stt_filters import (
    is_repeat_intent,
    is_substantive_utterance,
    listen_idle_message,
    pick_best_stt_text,
    repeat_last_question_message,
)
from engines.voice_registry import get_default_voice_id, get_voice, resolve_voice_for_language
from engines.tts_utils import ensure_pcm_s16le_bytes, is_speakable_text
from llm_worker import LlmWorker, PhraseBuffer, stream_chat_tokens
from providers.registry import create_stt
from streaming.audio_buffer import DuplexAudioState
from streaming.event_bus import VoiceEventBus, _NoOpBus, get_event_bus
from streaming.prompts import build_messages
from tts_worker import TtsWorker

logger = logging.getLogger(__name__)

SendJson = Callable[[str], Awaitable[None]]
SendBinary = Callable[[bytes], Awaitable[None]]


class InterviewSession:
    """Full-duplex voice session using dedicated STT/LLM/TTS workers."""

    def __init__(
        self,
        *,
        send_json: SendJson,
        send_binary: SendBinary,
        duplex: DuplexAudioState,
        language_hint: str | None = None,
        voice_id: str | None = None,
        candidate_name: str | None = None,
        event_bus: VoiceEventBus | _NoOpBus | None = None,
    ) -> None:
        self._send_json = send_json
        self._send_binary = send_binary
        self._duplex = duplex
        self._language_hint = language_hint
        self._voice_id = voice_id if voice_id else resolve_voice_for_language(language_hint)
        self._session_lang = resolve_session_language(language_hint)
        if interview_opening_enabled():
            self._candidate_name = None
        else:
            self._candidate_name = (candidate_name or '').strip() or None
        self._interview_phase = initial_interview_phase()
        self._name_retry_used = False
        self._intro_captured = False
        self._stt = create_stt()
        self._llm = LlmWorker()
        self._tts = TtsWorker()
        self._history: list[dict[str, str]] = []
        self._pending_final: str | None = None
        self._last_detected_lang: str | None = None
        self._last_stt_text = ''
        self._best_stt_text = ''
        self._processing = False
        self._empty_prompt_playing = False
        self._last_empty_prompt_at = 0.0
        self._last_idle_nudge_at = 0.0
        self._idle_task: asyncio.Task | None = None
        self._turn_tasks: list[asyncio.Task] = []
        self._end_utterance_task: asyncio.Task | None = None
        self._end_utterance_pending = False
        self.session_id = str(uuid.uuid4())
        self._barge_in_offset_ms = 0.0
        self._turn_audio_config_sent = False
        self._bus = event_bus if event_bus is not None else get_event_bus()
        self._closed = False

    @property
    def voice_id(self) -> str:
        return self._voice_id

    async def start(self) -> None:
        await self._stt.start(language_hint=self._language_hint)
        tts_hint = self._session_lang or self._language_hint
        await self._tts.start(language_hint=tts_hint, voice_id=self._voice_id)
        await self._bus.session_event(
            self.session_id,
            'session_start',
            stt='whisper',
            tts='f5',
            voice_id=self._voice_id,
            language=self._language_hint or 'auto',
        )

    async def close(self) -> None:
        self._closed = True
        self._cancel_listen_idle()
        for task in self._turn_tasks:
            if not task.done():
                task.cancel()
        self._turn_tasks.clear()
        await self._stt.close()
        await self._tts.close()
        await self._bus.session_event(self.session_id, 'session_end')

    async def play_greeting(self) -> None:
        if self._processing:
            return
        self._cancel_listen_idle()

        if interview_opening_enabled() and BOT_MODE == 'interview':
            text, script = opening_script(self._session_lang)
            self._interview_phase = InterviewPhase.WAITING_NAME
        else:
            from engines.demo_bot import _greeting_text

            name = self._candidate_name or 'Candidate'
            text, script = _greeting_text(name, self._session_lang)
            if BOT_MODE != 'interview':
                text = text if text else f'Hello {name}, welcome.'
            self._interview_phase = InterviewPhase.ACTIVE

        self._processing = True
        await self._duplex.begin_turn()
        await self._duplex.set_agent_speaking(True)
        self._turn_audio_config_sent = False
        await self._send_json(_evt('turn_start'))
        try:
            tts_route = pick_tts_route_for_session(self._session_lang, script)
            await self._tts.start(language_hint=tts_route, voice_id=self._voice_id)
            await self._send_json(_evt('assistant_delta', text=text))
            await self._stream_tts_phrase(text, tts_route)
            self._history.append({'role': 'assistant', 'content': text})
            await self._send_json(_evt('assistant_text', text=text))
        except Exception as exc:
            logger.exception('greeting failed')
            await self._send_json(_evt('error', message=str(exc)))
        finally:
            await self._duplex.set_agent_speaking(False)
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            self._processing = False
            self._turn_audio_config_sent = False

    async def on_listen_ready(self) -> None:
        """Client finished playing TTS — safe to start listen-idle timer."""
        if self._closed:
            return
        self._schedule_listen_idle()

    async def handle_barge_in(self, offset_ms: float) -> None:
        self._barge_in_offset_ms = offset_ms
        await self._bus.barge_in(self.session_id, offset_ms)

    def _note_stt_text(self, text: str, *, is_final: bool = False) -> None:
        cleaned = (text or '').strip()
        if not cleaned:
            return
        if is_final:
            self._last_stt_text = cleaned
        best = pick_best_stt_text(self._best_stt_text, cleaned)
        if best:
            self._best_stt_text = best

    async def on_pcm_chunk(self, chunk: bytes, *, rms_energy: float = 0.0) -> None:
        if self._closed:
            return
        if rms_energy > 0.02:
            self._cancel_listen_idle()
        await self._duplex.push_incoming(chunk)
        if await self._duplex.should_barge_in(rms_energy):
            await self._duplex.request_barge_in()
            await self._send_json(
                '{"type":"barge_in","message":"User interrupted agent"}'
            )

        async with self._duplex.lock:
            accept_stt = not self._duplex.agent_speaking
        events = await self._stt.push_pcm(chunk, rms_energy=rms_energy) if accept_stt else []
        for ev in events:
            self._note_stt_text(ev.text or '', is_final=ev.is_final)
            if ev.is_final:
                self._pending_final = ev.text
                if ev.language:
                    self._last_detected_lang = ev.language
                await self._send_json(
                    _evt('stt_final', text=ev.text, language=ev.language)
                )
                await self._bus.transcript(
                    self.session_id, ev.text or '', is_final=True, language=ev.language
                )
            else:
                await self._send_json(
                    _evt('stt_partial', text=ev.text, language=ev.language)
                )
                await self._bus.transcript(
                    self.session_id, ev.text or '', is_final=False, language=ev.language
                )

    async def on_end_utterance(self) -> None:
        if self._closed:
            return
        self._cancel_listen_idle()
        if self._end_utterance_task and not self._end_utterance_task.done():
            self._end_utterance_pending = True
            return
        self._end_utterance_task = asyncio.create_task(self._process_end_utterance())

    async def _cancel_active_turn(self) -> None:
        """Stop in-flight LLM/TTS so a new user utterance can be handled."""
        async with self._duplex.lock:
            agent_busy = self._duplex.agent_speaking or self._duplex.turn_in_progress
        if not agent_busy and not self._processing:
            return
        await self._duplex.request_barge_in()
        self._empty_prompt_playing = False
        for task in self._turn_tasks:
            if not task.done():
                task.cancel()
        self._turn_tasks.clear()

    async def _process_end_utterance(self) -> None:
        try:
            await self._send_json(_evt('stt_processing'))
            async with self._duplex.lock:
                agent_speaking = self._duplex.agent_speaking

            if agent_speaking or self._processing:
                await self._cancel_active_turn()
                await asyncio.sleep(0.05)

            events = await self._stt.flush()
            text = ''
            detected_lang = self._last_detected_lang
            for ev in events:
                if ev.is_final and (ev.text or '').strip():
                    text = ev.text.strip()
                    if ev.language:
                        detected_lang = ev.language
            if not text:
                text = pick_best_stt_text(
                    self._pending_final,
                    self._best_stt_text,
                    self._last_stt_text,
                )
            self._pending_final = None

            if text and self._utterance_accepted(text):
                if detected_lang:
                    self._last_detected_lang = detected_lang
                await self._send_json(
                    _evt('stt_final', text=text, language=self._last_detected_lang)
                )
                await self._bus.transcript(
                    self.session_id,
                    text,
                    is_final=True,
                    language=self._last_detected_lang,
                )
                self._last_stt_text = ''
                self._best_stt_text = ''
                if self._interview_phase != InterviewPhase.ACTIVE:
                    task = asyncio.create_task(self._handle_opening_utterance(text))
                    self._turn_tasks.append(task)
                    return
                if is_repeat_intent(text):
                    task = asyncio.create_task(self._repeat_last_question())
                    self._turn_tasks.append(task)
                    return
                task = asyncio.create_task(self._run_turn(text))
                self._turn_tasks.append(task)
                return

            await self._prompt_empty_utterance()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('end_utterance processing failed')
            await self._send_json(
                _evt(
                    'error',
                    message='Could not process your speech. Please try again.',
                )
            )
            self._schedule_listen_idle()
        finally:
            if self._end_utterance_pending:
                self._end_utterance_pending = False
                self._end_utterance_task = asyncio.create_task(self._process_end_utterance())
            else:
                self._end_utterance_task = None

    def _utterance_accepted(self, text: str) -> bool:
        if self._interview_phase == InterviewPhase.WAITING_NAME:
            return len(text.strip()) >= 2
        return is_substantive_utterance(text, min_chars=STREAM_STT_MIN_CHARS)

    async def _handle_opening_utterance(self, text: str) -> None:
        if self._interview_phase == InterviewPhase.WAITING_NAME:
            name = extract_candidate_name(text)
            if name:
                self._candidate_name = name
                welcome, script = welcome_and_intro_script(name, self._session_lang)
                self._interview_phase = InterviewPhase.AWAIT_INTRO
                await self._run_canned_reply(text, welcome, script)
                return
            if not self._name_retry_used:
                self._name_retry_used = True
                retry, script = name_retry_script(self._session_lang)
                await self._run_canned_reply(text, retry, script)
                return
            welcome, script = welcome_and_intro_script(None, self._session_lang)
            self._interview_phase = InterviewPhase.AWAIT_INTRO
            await self._run_canned_reply(text, welcome, script)
            return

        if self._interview_phase == InterviewPhase.AWAIT_INTRO:
            self._interview_phase = InterviewPhase.ACTIVE
            self._intro_captured = True
            await self._run_turn(text, intro_follow_up=True)

    async def _run_canned_reply(
        self,
        user_text: str,
        assistant_text: str,
        reply_script: str,
    ) -> None:
        """Speak a fixed reply (off-topic refusal) without calling the LLM."""
        self._processing = True
        self._barge_in_offset_ms = 0.0
        self._turn_audio_config_sent = False
        await self._duplex.begin_turn()
        await self._duplex.set_agent_speaking(True)
        await self._send_json(_evt('turn_start'))
        await self._bus.turn_event(self.session_id, 'turn_start')
        try:
            self._history.append({'role': 'user', 'content': user_text})
            tts_route = pick_tts_route_for_session(self._session_lang, reply_script)
            await self._tts.start(language_hint=tts_route, voice_id=self._voice_id)
            await self._send_json(_evt('assistant_delta', text=assistant_text))
            await self._stream_tts_phrase(assistant_text, tts_route)
            self._history.append({'role': 'assistant', 'content': assistant_text})
            await self._send_json(_evt('assistant_text', text=assistant_text))
            await self._bus.session_event(
                self.session_id, 'assistant_text', text=assistant_text
            )
        except Exception as exc:
            logger.exception('canned reply failed')
            await self._send_json(_evt('error', message=str(exc)))
        finally:
            await self._duplex.set_agent_speaking(False)
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            await self._bus.turn_event(self.session_id, 'turn_end')
            self._processing = False
            self._turn_audio_config_sent = False

    async def _run_turn(self, user_text: str, *, intro_follow_up: bool = False) -> None:
        self._processing = True
        self._barge_in_offset_ms = 0.0
        self._turn_audio_config_sent = False
        await self._duplex.begin_turn()
        await self._duplex.set_agent_speaking(True)
        await self._send_json(_evt('turn_start'))
        await self._bus.turn_event(self.session_id, 'turn_start')
        full_reply: list[str] = []
        interjection_played = False
        reply_script = pick_reply_script_for_session(
            self._session_lang, self._last_detected_lang, user_text
        )

        if is_off_topic_interview_question(user_text):
            refusal, script = off_topic_refusal_message(self._session_lang, reply_script)
            await self._run_canned_reply(user_text, refusal, script)
            return

        try:
            intro_hint = INTRO_FOLLOW_UP_HINT if intro_follow_up else None
            extra_system = build_extra_system(
                self._session_lang,
                reply_script,
                intro_follow_up=intro_hint,
            )
            messages = build_messages(
                history=self._history[-16:],
                user_text=user_text,
                extra_system=extra_system,
                candidate_name=self._candidate_name,
            )
            self._history.append({'role': 'user', 'content': user_text})

            tts_route = pick_tts_route_for_session(self._session_lang, reply_script)
            await self._tts.start(language_hint=tts_route, voice_id=self._voice_id)

            phrase_q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=8)
            first_token_event = asyncio.Event()
            cancel = self._duplex.cancel_generation
            strict_gate = should_strict_script_gate() and self._session_lang in (
                'hi',
                'hinglish',
            )
            finalized_text: list[str] = []

            async def _llm_producer() -> None:
                splitter = PhraseBuffer()
                try:
                    async for token in stream_chat_tokens(
                        messages, temperature=OPENAI_VOICE_TEMPERATURE
                    ):
                        if cancel.is_set():
                            break
                        if not first_token_event.is_set():
                            first_token_event.set()
                        full_reply.append(token)
                        await self._send_json(_evt('assistant_delta', text=token))
                        if not strict_gate:
                            for phrase in splitter.push(token):
                                if cancel.is_set():
                                    break
                                await phrase_q.put(phrase)
                    if strict_gate and not cancel.is_set():
                        raw = ''.join(full_reply).strip()
                        text, phrases = await finalize_assistant_for_tts(
                            messages,
                            raw,
                            self._session_lang,
                            reply_script,
                        )
                        finalized_text.append(text)
                        for phrase in phrases:
                            await phrase_q.put(phrase)
                    elif not strict_gate:
                        remainder = splitter.flush()
                        if remainder and not cancel.is_set():
                            await phrase_q.put(remainder)
                finally:
                    await phrase_q.put(None)

            async def _interjection_watcher() -> None:
                nonlocal interjection_played
                try:
                    await asyncio.wait_for(
                        first_token_event.wait(),
                        timeout=INTERJECTION_TIMEOUT_MS / 1000.0,
                    )
                except asyncio.TimeoutError:
                    if cancel.is_set() or interjection_played:
                        return
                    clip = pick_interjection(reply_script)
                    if clip is None:
                        return
                    interjection_played = True
                    await self._stream_cached_interjection(clip)

            async def _tts_consumer() -> None:
                while True:
                    phrase = await phrase_q.get()
                    if phrase is None:
                        break
                    if cancel.is_set():
                        while not phrase_q.empty():
                            phrase_q.get_nowait()
                        break
                    await self._stream_tts_phrase(phrase, tts_route)

            await asyncio.gather(
                _interjection_watcher(),
                _llm_producer(),
                _tts_consumer(),
            )

            assistant_text = (
                finalized_text[0]
                if finalized_text
                else ''.join(full_reply).strip()
            )
            if cancel.is_set() and self._barge_in_offset_ms > 0:
                chars_spoken = int((self._barge_in_offset_ms / 1000.0) * 15)
                if chars_spoken < len(assistant_text):
                    truncated = assistant_text[:chars_spoken]
                    last_space = truncated.rfind(' ')
                    assistant_text = (
                        truncated[:last_space] if last_space > 0 else truncated
                    )

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
            await self._duplex.set_agent_speaking(False)
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            await self._bus.turn_event(self.session_id, 'turn_end')
            self._processing = False
            self._turn_audio_config_sent = False

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
        self._turn_audio_config_sent = False
        await self._duplex.begin_turn()
        await self._duplex.set_agent_speaking(True)
        await self._send_json(_evt('turn_start'))
        try:
            ack, script = repeat_last_question_message(self._session_lang)
            tts_route = pick_tts_route_for_session(self._session_lang, script)
            await self._tts.start(language_hint=tts_route, voice_id=self._voice_id)
            await self._send_json(_evt('assistant_delta', text=ack))
            await self._stream_tts_phrase(ack, tts_route)
            await self._send_json(_evt('assistant_delta', text=last_assistant))
            await self._stream_tts_phrase(last_assistant, tts_route)
            await self._send_json(_evt('assistant_text', text=f'{ack} {last_assistant}'))
        except Exception as exc:
            logger.exception('repeat question failed')
            await self._send_json(_evt('error', message=str(exc)))
        finally:
            await self._duplex.set_agent_speaking(False)
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            self._processing = False
            self._turn_audio_config_sent = False

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
        hint, script = empty_utterance_message(self._session_lang)
        self._empty_prompt_playing = True
        await self._send_json(_evt('assistant_text', text=hint))
        tts_route = pick_tts_route_for_session(self._session_lang, script)
        try:
            await self._stream_tts_phrase(hint, tts_route)
        except Exception:
            logger.exception('empty utterance TTS failed')
        finally:
            self._empty_prompt_playing = False
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
            if self._processing or self._closed:
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
        self._turn_audio_config_sent = False
        await self._duplex.begin_turn()
        await self._duplex.set_agent_speaking(True)
        await self._send_json(_evt('turn_start'))
        try:
            tts_route = pick_tts_route_for_session(self._session_lang, script)
            await self._tts.start(language_hint=tts_route, voice_id=self._voice_id)
            await self._send_json(_evt('assistant_text', text=hint))
            await self._stream_tts_phrase(hint, tts_route)
        except Exception:
            logger.exception('listen idle nudge failed')
        finally:
            await self._duplex.set_agent_speaking(False)
            await self._duplex.end_turn()
            await self._send_json(_evt('turn_end'))
            self._processing = False
            self._turn_audio_config_sent = False

    async def _stream_cached_interjection(self, clip) -> None:
        try:
            await self._send_json(_evt('assistant_delta', text=clip.text))
            if not self._turn_audio_config_sent:
                await self._send_json(
                    _evt('audio_config', sample_rate=clip.sample_rate, format='pcm_s16le')
                )
                self._turn_audio_config_sent = True
            await self._send_binary(clip.pcm_s16le)
        except Exception:
            logger.exception('interjection stream failed')

    async def _stream_tts_phrase(self, phrase: str, tts_lang: str) -> None:
        if self._duplex.cancel_generation.is_set():
            return
        cleaned = (phrase or '').strip()
        if not cleaned or not is_speakable_text(cleaned):
            return
        try:
            async for chunk in self._tts.synthesize_stream(cleaned):
                if self._duplex.cancel_generation.is_set():
                    break
                sr = chunk.sample_rate or 24000
                pcm = ensure_pcm_s16le_bytes(chunk.pcm_s16le)
                if not pcm:
                    continue
                if not self._turn_audio_config_sent:
                    await self._send_json(
                        _evt('audio_config', sample_rate=sr, format='pcm_s16le')
                    )
                    self._turn_audio_config_sent = True
                await self._send_binary(pcm)
        except Exception as exc:
            logger.exception('TTS phrase failed')
            await self._send_json(_evt('error', message=f'TTS failed: {exc}'))


def _evt(event_type: str, **fields) -> str:
    payload = {'type': event_type, **fields}
    return json.dumps(payload, ensure_ascii=False)

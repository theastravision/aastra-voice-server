"""Full-duplex streaming voice WebSocket — /ws/voice."""

from __future__ import annotations

import json
import logging
import struct

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth import require_ws_api_key
from config import STT_PROVIDER, STREAM_ALLOW_PUBLIC, STREAM_SAMPLE_RATE, STREAM_SILENCE_END_MS
from server import InterviewSession
from streaming.audio_buffer import DuplexAudioState
from streaming.event_bus import get_event_bus
from streaming.protocol import WsType, json_event

logger = logging.getLogger(__name__)
router = APIRouter()


def _rms_pcm_s16le(chunk: bytes) -> float:
    if len(chunk) < 2:
        return 0.0
    n = len(chunk) // 2
    samples = struct.unpack(f'<{n}h', chunk[: n * 2])
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return (mean_sq ** 0.5) / 32768.0


def _config_key(payload: dict) -> tuple:
    return (
        payload.get('language'),
        payload.get('voice_id'),
        (payload.get('candidate_name') or '').strip() or None,
    )


class _ClientTransport:
    """Drop outbound frames after the browser disconnects (avoids ASGI RuntimeError)."""

    __slots__ = ('_alive', '_ws')

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._alive = True

    def close(self) -> None:
        self._alive = False

    async def send_json(self, payload: str) -> None:
        if not self._alive:
            return
        try:
            await self._ws.send_text(payload)
        except WebSocketDisconnect:
            self._alive = False
        except RuntimeError as exc:
            msg = str(exc).lower()
            if 'websocket' in msg or 'closed' in msg or 'completed' in msg:
                self._alive = False
                return
            raise

    async def send_binary(self, data: bytes) -> None:
        if not self._alive:
            return
        try:
            await self._ws.send_bytes(data)
        except WebSocketDisconnect:
            self._alive = False
        except RuntimeError as exc:
            msg = str(exc).lower()
            if 'websocket' in msg or 'closed' in msg or 'completed' in msg:
                self._alive = False
                return
            raise


@router.websocket('/ws/voice')
async def ws_voice(websocket: WebSocket):
    if not STREAM_ALLOW_PUBLIC:
        if not await require_ws_api_key(websocket):
            return
    await websocket.accept()

    duplex = DuplexAudioState(sample_rate=STREAM_SAMPLE_RATE)
    transport = _ClientTransport(websocket)

    session: InterviewSession | None = None

    try:
        while True:
            message = await websocket.receive()
            if message.get('type') == 'websocket.disconnect':
                break

            if 'bytes' in message and message['bytes'] is not None:
                chunk = message['bytes']
                if session is None:
                    await transport.send_json(
                        json_event(WsType.ERROR, message='Send config JSON before audio')
                    )
                    continue
                energy = _rms_pcm_s16le(chunk)
                await session.on_pcm_chunk(chunk, rms_energy=energy)
                continue

            raw = message.get('text')
            if not raw:
                continue

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await transport.send_json(json_event(WsType.ERROR, message='Invalid JSON'))
                continue

            msg_type = payload.get('type', '')

            if msg_type == WsType.PING.value:
                await transport.send_json(json_event(WsType.PONG))
                continue

            if msg_type == WsType.CONFIG.value:
                lang = payload.get('language')
                candidate = payload.get('candidate_name')
                voice_id = payload.get('voice_id')
                greet_raw = payload.get('greet', False)
                greet = greet_raw is True or (
                    isinstance(greet_raw, str) and greet_raw.lower() in ('1', 'true', 'yes')
                )
                new_key = _config_key(payload)
                reused = False
                greeted = False

                if session is not None and session.config_key == new_key:
                    reused = True
                    if greet and not session.is_greeted:
                        greeted = await session.play_greeting()
                    elif greet and session.is_greeted:
                        greeted = False
                else:
                    if session:
                        await session.close()
                    session = InterviewSession(
                        send_json=transport.send_json,
                        send_binary=transport.send_binary,
                        duplex=duplex,
                        language_hint=lang,
                        voice_id=voice_id,
                        candidate_name=candidate,
                        event_bus=get_event_bus(),
                    )
                    await session.start()
                    if greet:
                        greeted = await session.play_greeting()
                    else:
                        greeted = False

                await transport.send_json(
                    json_event(
                        WsType.CONFIG,
                        ok=True,
                        session_id=session.session_id,
                        greeted=greeted,
                        reused=reused,
                        stt=STT_PROVIDER,
                        tts='f5',
                        voice_id=session.voice_id,
                        sample_rate=STREAM_SAMPLE_RATE,
                        silence_end_ms=STREAM_SILENCE_END_MS,
                        ws_path='/ws/voice',
                    )
                )
                continue

            if session is None:
                await transport.send_json(json_event(WsType.ERROR, message='Not configured'))
                continue

            if msg_type == WsType.END_UTTERANCE.value:
                await session.on_end_utterance()
            elif msg_type == WsType.LISTEN_READY.value:
                await session.on_listen_ready()
            elif msg_type == WsType.BARGE_IN.value:
                offset = payload.get('offset_ms', 0.0)
                await duplex.request_barge_in()
                await session.handle_barge_in(offset)
                await transport.send_json(json_event(WsType.BARGE_IN, ok=True))
            else:
                await transport.send_json(json_event(WsType.ERROR, message=f'Unknown type: {msg_type}'))

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception('ws/voice session error')
    finally:
        transport.close()
        if session:
            await session.close()

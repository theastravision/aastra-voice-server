"""Full-duplex streaming voice WebSocket — /ws/voice."""

from __future__ import annotations

import json
import logging
import struct

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth import require_ws_api_key
from config import STREAM_ALLOW_PUBLIC, STREAM_SAMPLE_RATE
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


@router.websocket('/ws/voice')
async def ws_voice(websocket: WebSocket):
    if not STREAM_ALLOW_PUBLIC:
        if not await require_ws_api_key(websocket):
            return
    await websocket.accept()

    duplex = DuplexAudioState(sample_rate=STREAM_SAMPLE_RATE)

    async def send_json(payload: str) -> None:
        await websocket.send_text(payload)

    async def send_binary(data: bytes) -> None:
        await websocket.send_bytes(data)

    session: InterviewSession | None = None

    try:
        while True:
            message = await websocket.receive()
            if message.get('type') == 'websocket.disconnect':
                break

            if 'bytes' in message and message['bytes'] is not None:
                chunk = message['bytes']
                if session is None:
                    await send_json(
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
                await send_json(json_event(WsType.ERROR, message='Invalid JSON'))
                continue

            msg_type = payload.get('type', '')

            if msg_type == WsType.PING.value:
                await send_json(json_event(WsType.PONG))
                continue

            if msg_type == WsType.CONFIG.value:
                lang = payload.get('language')
                candidate = payload.get('candidate_name')
                greet_raw = payload.get('greet', False)
                greet = greet_raw is True or (
                    isinstance(greet_raw, str) and greet_raw.lower() in ('1', 'true', 'yes')
                )
                if session:
                    await session.close()
                session = InterviewSession(
                    send_json=send_json,
                    send_binary=send_binary,
                    duplex=duplex,
                    language_hint=lang,
                    voice_id=payload.get('voice_id'),
                    candidate_name=candidate,
                    event_bus=get_event_bus(),
                )
                await session.start()
                greeted = False
                if greet:
                    await session.play_greeting()
                    greeted = True
                await send_json(
                    json_event(
                        WsType.CONFIG,
                        ok=True,
                        session_id=session.session_id,
                        greeted=greeted,
                        stt='whisper_chunk',
                        tts='f5',
                        voice_id=session.voice_id,
                        sample_rate=STREAM_SAMPLE_RATE,
                        ws_path='/ws/voice',
                    )
                )
                continue

            if session is None:
                await send_json(json_event(WsType.ERROR, message='Not configured'))
                continue

            if msg_type == WsType.END_UTTERANCE.value:
                await session.on_end_utterance()
            elif msg_type == WsType.LISTEN_READY.value:
                await session.on_listen_ready()
            elif msg_type == WsType.BARGE_IN.value:
                offset = payload.get('offset_ms', 0.0)
                await duplex.request_barge_in()
                await session.handle_barge_in(offset)
                await send_json(json_event(WsType.BARGE_IN, ok=True))
            else:
                await send_json(json_event(WsType.ERROR, message=f'Unknown type: {msg_type}'))

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception('ws/voice session error')
    finally:
        if session:
            await session.close()

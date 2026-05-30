"""WebSocket /ws/audio — matches Django XyzAudioProvider protocol."""

from __future__ import annotations

import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth import require_ws_api_key
from engines.f5_tts_engine import synthesize_mp3
from engines.whisper_stt import transcribe_bytes

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket('/ws/audio')
async def ws_audio(websocket: WebSocket):
    if not await require_ws_api_key(websocket):
        return
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({'error': 'Invalid JSON payload.'})
                continue
            event = payload.get('event')
            if event == 'tts':
                text = (payload.get('text') or '').strip()
                voice = payload.get('voice') or 'astra'
                if not text:
                    await websocket.send_json({'error': 'text required'})
                    continue
                try:
                    audio, mime = synthesize_mp3(text, voice=voice)
                    await websocket.send_json({
                        'audio_base64': base64.b64encode(audio).decode('ascii'),
                        'mime': mime,
                    })
                except Exception as exc:
                    logger.exception('TTS failed')
                    await websocket.send_json({'error': str(exc)})
            elif event == 'stt':
                audio_b64 = payload.get('audio_base64') or ''
                filename = payload.get('filename') or 'audio.webm'
                if not audio_b64:
                    await websocket.send_json({'error': 'audio_base64 required'})
                    continue
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                    result = transcribe_bytes(audio_bytes, filename=filename)
                    await websocket.send_json({
                        'text': result['text'],
                        'detected_language': result['detected_language'],
                    })
                except Exception as exc:
                    logger.exception('STT failed')
                    await websocket.send_json({'error': str(exc)})
            else:
                await websocket.send_json({'error': f'Unknown event: {event}'})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception('WebSocket session error')
        try:
            await websocket.close(code=1011)
        except Exception:
            pass

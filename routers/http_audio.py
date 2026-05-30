"""REST endpoints for Salad Container Gateway and manual testing."""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from auth import require_api_key
from engines.conversation import parse_history_json, voice_turn
from engines.audio_convert import AudioDecodeError
from engines.f5_tts_engine import synthesize_audio
from engines.whisper_stt import transcribe_bytes

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1', dependencies=[Depends(require_api_key)])


class TtsRequest(BaseModel):
    text: str
    voice: str = 'astra'
    lang: str | None = None


class TranscribeResponse(BaseModel):
    text: str
    detected_language: str
    english_text: str | None = None


@router.post('/transcribe', response_model=TranscribeResponse)
async def transcribe(audio: UploadFile = File(...)):
    content = await audio.read()
    try:
        result = transcribe_bytes(content, filename=audio.filename or 'audio.webm')
    except AudioDecodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    text = result['text']
    return TranscribeResponse(
        text=text,
        english_text=text,
        detected_language=result['detected_language'],
    )


@router.post('/tts')
async def tts(request: TtsRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail='text required')
    try:
        audio, mime = synthesize_audio(
            request.text,
            voice=request.voice,
            lang=request.lang,
        )
    except Exception as exc:
        logger.exception('TTS failed')
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(content=audio, media_type=mime)


@router.post('/voice-turn')
async def voice_turn_endpoint(
    audio: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    lang_hint: str = Form(default='auto'),
    history: str | None = Form(default=None),
):
    content = await audio.read()
    try:
        hist = parse_history_json(history)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = voice_turn(
            content,
            filename=audio.filename or 'audio.webm',
            lang_hint=lang_hint,
            history=hist,
            session_id=session_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('voice-turn failed')
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result

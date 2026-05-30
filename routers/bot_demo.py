"""Public demo conversational bot (no auth) — testing via ngrok."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from config import (
    ALLOW_PUBLIC_DEMO,
    BOT_MODE,
    DEMO_CANDIDATE_NAME,
    INTERVIEW_JOB_TITLE,
    INTERVIEW_OPENING_ENABLED,
    INTERVIEW_STRICT_MODE,
    STT_PROVIDER,
    TTS_PROVIDER,
)
from providers.registry import auto_tts_provider
from engines import demo_bot
from engines.audio_convert import AudioDecodeError

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1/demo', tags=['demo-bot'])


def _ensure_demo_enabled() -> None:
    if not ALLOW_PUBLIC_DEMO:
        raise HTTPException(status_code=403, detail='Public demo bot is disabled.')


class StartRequest(BaseModel):
    candidate_name: str = 'Aashish'
    language: str = 'en'


class DemoTtsRequest(BaseModel):
    text: str
    language: str = 'en'
    voice_id: str | None = None


@router.get('/config')
async def demo_config():
    _ensure_demo_enabled()
    from core.model_state import models_ready, warmup_error

    from engines.voice_registry import get_default_voice_id, list_voices

    voices = [
        {
            'id': v.id,
            'display_name': v.display_name,
            'language': v.language,
        }
        for v in list_voices()
    ]
    return {
        'candidate_name': DEMO_CANDIDATE_NAME,
        'bot_mode': BOT_MODE,
        'interview_strict_mode': BOT_MODE == 'interview' and INTERVIEW_STRICT_MODE,
        'interview_opening_enabled': BOT_MODE == 'interview' and INTERVIEW_OPENING_ENABLED,
        'interview_job_title': INTERVIEW_JOB_TITLE,
        'stt_provider': STT_PROVIDER,
        'tts_provider': auto_tts_provider(),
        'default_voice_id': get_default_voice_id(),
        'voices': voices,
        'models_ready': models_ready(),
        'warmup_error': warmup_error(),
        'ws_path': '/ws/voice',
    }


@router.post('/start')
async def demo_start(body: StartRequest = StartRequest()):
    _ensure_demo_enabled()
    from config import DEMO_CANDIDATE_NAME

    name = (body.candidate_name or DEMO_CANDIDATE_NAME or 'Aashish').strip()
    try:
        return demo_bot.start_session(name, language=body.language)
    except Exception as exc:
        logger.exception('demo start failed')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post('/turn')
async def demo_turn(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    _ensure_demo_enabled()
    content = await audio.read()
    if len(content) < 2048:
        raise HTTPException(
            status_code=422,
            detail='Audio clip too short; speak a bit longer and try again.',
        )
    try:
        return demo_bot.process_turn(session_id, content, filename=audio.filename or 'audio.webm')
    except AudioDecodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('demo turn failed')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post('/end')
async def demo_end(session_id: str = Form(...)):
    _ensure_demo_enabled()
    return demo_bot.end_session(session_id)


@router.get('/interview-names')
async def demo_interview_names():
    _ensure_demo_enabled()
    from engines.name_samples import list_interview_name_entries

    entries = list_interview_name_entries()
    return {
        'names': entries,
        'total': len(entries),
        'with_audio': sum(1 for e in entries if e.get('has_audio')),
        'samples_dir': 'data/name-samples',
    }


@router.get('/edge-voices')
async def demo_edge_voices():
    _ensure_demo_enabled()
    from engines.name_samples import list_edge_voice_entries

    entries = list_edge_voice_entries()
    return {
        'voices': entries,
        'total': len(entries),
        'with_audio': sum(1 for e in entries if e.get('has_audio')),
        'samples_dir': 'data/voice-samples',
    }


@router.post('/tts')
async def demo_tts(body: DemoTtsRequest):
    """Generate WAV audio for English, Hindi, or Hinglish (public demo)."""
    _ensure_demo_enabled()
    text = (body.text or '').strip()
    if not text:
        raise HTTPException(status_code=400, detail='text required')
    lang = (body.language or 'en').lower().strip()
    if lang not in ('en', 'hi', 'hinglish'):
        raise HTTPException(status_code=400, detail='language must be en, hi, or hinglish')
    try:
        from tts_worker import synthesize_wav_bytes

        audio, mime = await synthesize_wav_bytes(
            text,
            reply_script=lang,
            voice_id=body.voice_id,
        )
    except Exception as exc:
        logger.exception('demo TTS failed language=%s', lang)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not audio:
        raise HTTPException(status_code=422, detail='TTS produced no audio')
    return Response(content=audio, media_type=mime)


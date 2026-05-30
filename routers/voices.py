"""Voice registry CRUD API."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from auth import require_api_key
from config import ALLOW_PUBLIC_DEMO
from engines.f5_tts_engine import get_manager
from engines.voice_registry import (
    delete_voice,
    get_default_voice_id,
    get_voice,
    list_voices,
    save_voice,
    slugify,
    voice_assets_dir,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1/voices', tags=['voices'])


class VoiceOut(BaseModel):
    id: str
    display_name: str
    language: str
    ref_audio: str
    ref_text: str
    source: str
    created_at: str


def _optional_auth():
    if ALLOW_PUBLIC_DEMO:
        return None
    return Depends(require_api_key)


@router.get('', response_model=list[VoiceOut])
async def list_all_voices():
    return [
        VoiceOut(
            id=v.id,
            display_name=v.display_name,
            language=v.language,
            ref_audio=v.ref_audio,
            ref_text=v.ref_text,
            source=v.source,
            created_at=v.created_at,
        )
        for v in list_voices()
    ]


@router.get('/default')
async def default_voice():
    return {'default_voice_id': get_default_voice_id()}


@router.post('', dependencies=[Depends(require_api_key)])
async def create_voice(
    display_name: str = Form(...),
    language: str = Form('en'),
    ref_text: str = Form(...),
    ref_audio: UploadFile = File(...),
    set_default: bool = Form(False),
):
    voice_id = slugify(display_name)
    dest_dir = voice_assets_dir(voice_id)
    dest = dest_dir / 'ref.wav'
    content = await ref_audio.read()
    if len(content) < 1000:
        raise HTTPException(status_code=400, detail='Reference audio too short')
    dest.write_bytes(content)
    rel = str(dest.relative_to(Path(__file__).resolve().parents[1])).replace('\\', '/')
    profile = save_voice(
        voice_id=voice_id,
        display_name=display_name,
        language=language,
        ref_audio_rel=rel,
        ref_text=ref_text.strip(),
        source='upload',
        set_default=set_default,
    )
    try:
        get_manager().invalidate_voice(voice_id)
    except Exception:
        pass
    return VoiceOut(
        id=profile.id,
        display_name=profile.display_name,
        language=profile.language,
        ref_audio=profile.ref_audio,
        ref_text=profile.ref_text,
        source=profile.source,
        created_at=profile.created_at,
    )


@router.delete('/{voice_id}', dependencies=[Depends(require_api_key)])
async def remove_voice(voice_id: str):
    if not delete_voice(voice_id):
        raise HTTPException(status_code=404, detail='Voice not found')
    try:
        get_manager().invalidate_voice(voice_id)
    except Exception:
        pass
    assets = voice_assets_dir(voice_id)
    if assets.is_dir():
        shutil.rmtree(assets, ignore_errors=True)
    return {'ok': True}


@router.post('/{voice_id}/preview', dependencies=[Depends(require_api_key)])
async def preview_voice(voice_id: str, text: str = Form('Hello, this is a voice preview.')):
    v = get_voice(voice_id)
    if not v:
        raise HTTPException(status_code=404, detail='Voice not found')
    from engines.f5_tts_engine import synthesize_audio

    audio, mime = synthesize_audio(text, voice=voice_id)
    return Response(content=audio, media_type=mime)

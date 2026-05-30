"""STT training job API."""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from auth import require_api_key
from config import ALLOW_PUBLIC_DEMO, HINGLISH_SYNTH_MAX_ROWS, HINGLISH_SYNTH_VOICE_ID
from training.import_kokoro_dataset import import_kokoro_dataset
from training.job_runner import (
    create_job,
    get_job,
    load_jobs,
    start_job_async,
    start_synth_job_async,
    upsert_job,
)
from training.prep_whisper_corpus import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1/training', tags=['training'])

_WRITE_DEPS = [] if ALLOW_PUBLIC_DEMO else [Depends(require_api_key)]


def _find_dataset_root(base: Path) -> Path | None:
    """Locate Kokoro layout (metadata.csv + wavs/) inside an extracted tree."""
    if (base / 'metadata.csv').is_file() or (base / 'wavs').is_dir():
        return base
    for meta in base.rglob('metadata.csv'):
        return meta.parent
    for wavs in base.rglob('wavs'):
        if wavs.is_dir() and any(wavs.iterdir()):
            return wavs.parent
    return None


def _extract_upload_zip(raw: bytes, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / 'upload.zip'
    zip_path.write_bytes(raw)
    extract_to = dest / 'extracted'
    extract_to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_to)
    root = _find_dataset_root(extract_to)
    if root is None:
        raise HTTPException(
            status_code=422,
            detail=(
                'ZIP must contain Kokoro layout: metadata.csv and wavs/ folder, '
                'or individual audio files for /jobs upload.'
            ),
        )
    return root


class JobOut(BaseModel):
    id: str
    language: str
    status: str
    job_type: str = 'whisper_finetune'
    sample_count: int
    hours: float
    rows_synthesized: int = 0
    error: str | None = None
    whisper_path: str | None = None
    manifest_path: str | None = None
    register_voice: bool = False
    voice_name: str | None = None
    created_at: str
    updated_at: str


def _to_out(j) -> JobOut:
    return JobOut(
        id=j.id,
        language=j.language,
        status=j.status,
        job_type=getattr(j, 'job_type', 'whisper_finetune'),
        sample_count=j.sample_count,
        hours=j.hours,
        rows_synthesized=getattr(j, 'rows_synthesized', 0),
        error=j.error,
        whisper_path=j.whisper_path,
        manifest_path=getattr(j, 'manifest_path', None),
        register_voice=j.register_voice,
        voice_name=j.voice_name,
        created_at=j.created_at,
        updated_at=j.updated_at,
    )


@router.get('/jobs', response_model=list[JobOut])
async def list_jobs():
    return [_to_out(j) for j in load_jobs()]


@router.get('/jobs/{job_id}', response_model=JobOut)
async def get_job_detail(job_id: str):
    j = get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail='Job not found')
    return _to_out(j)


@router.post('/jobs', dependencies=_WRITE_DEPS)
async def start_training_job(
    language: str = Form(...),
    files: list[UploadFile] = File(...),
    register_voice: bool = Form(False),
    voice_name: str | None = Form(None),
):
    if language not in ('en', 'hi', 'hinglish'):
        raise HTTPException(status_code=400, detail='language must be en, hi, or hinglish')
    if not files:
        raise HTTPException(status_code=400, detail='Select at least one audio file or ZIP')

    job = create_job(
        language=language,
        register_voice=register_voice,
        voice_name=voice_name,
    )
    job.status = 'preprocessing'
    upsert_job(job)

    total = 0
    hours = 0.0
    tmp_dir = Path(tempfile.mkdtemp(prefix='train-upload-'))
    kokoro_root: Path | None = None
    try:
        for upload in files:
            name = upload.filename or 'audio.wav'
            raw = await upload.read()
            if not raw:
                continue
            if name.lower().endswith('.zip'):
                kokoro_root = _extract_upload_zip(raw, tmp_dir / f'zip-{name}')
                continue
            dest = tmp_dir / Path(name).name
            dest.write_bytes(raw)
            try:
                _wav, _text, dur = ingest_file(dest, language)
                total += 1
                hours += dur / 3600.0
            except Exception as exc:
                logger.warning('Skip %s: %s', name, exc)

        if kokoro_root is not None:
            result = import_kokoro_dataset(
                kokoro_root,
                language=language,
                voice_name=voice_name if register_voice else None,
                start_whisper_job=False,
            )
            total = max(total, result.get('sample_count', 0))
            hours = max(hours, result.get('hours', 0.0))

        job.sample_count = total
        job.hours = round(hours, 3)
        if total == 0:
            job.status = 'failed'
            job.error = 'No valid audio ingested'
            upsert_job(job)
            raise HTTPException(status_code=422, detail=job.error)

        job.status = 'queued'
        upsert_job(job)
        start_job_async(job.id)
        return _to_out(job)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post('/import-kokoro', dependencies=_WRITE_DEPS)
async def import_kokoro(
    language: str = Form('hi'),
    voice_name: str | None = Form(None),
    start_whisper_job: bool = Form(True),
    dataset_path: str | None = Form(None),
    dataset_zip: UploadFile | None = File(None),
):
    """Import Kokoro dataset from browser ZIP upload or server-side folder path."""
    if language not in ('en', 'hi', 'hinglish'):
        raise HTTPException(status_code=400, detail='language must be en, hi, or hinglish')

    tmp_dir: Path | None = None
    try:
        if dataset_zip and dataset_zip.filename:
            raw = await dataset_zip.read()
            if not raw:
                raise HTTPException(status_code=400, detail='Empty ZIP file')
            tmp_dir = Path(tempfile.mkdtemp(prefix='kokoro-upload-'))
            path = _extract_upload_zip(raw, tmp_dir)
        elif dataset_path and dataset_path.strip():
            path = Path(dataset_path.strip())
            if not path.is_dir():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f'Server path not found: {dataset_path}. '
                        'Upload a ZIP from your computer instead.'
                    ),
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    'Upload a Kokoro dataset ZIP (metadata.csv + wavs/ folder) '
                    'from your computer.'
                ),
            )

        result = import_kokoro_dataset(
            path,
            language=language,
            voice_name=voice_name,
            start_whisper_job=start_whisper_job,
        )
        if result.get('sample_count', 0) == 0:
            raise HTTPException(
                status_code=422,
                detail='No audio clips found in dataset. Check metadata.csv and wavs/.',
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('kokoro import failed')
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class HinglishSynthIn(BaseModel):
    max_rows: int = HINGLISH_SYNTH_MAX_ROWS
    voice_id: str = HINGLISH_SYNTH_VOICE_ID
    dry_run: bool = False


@router.post('/hinglish/synthesize', dependencies=_WRITE_DEPS)
async def synthesize_hinglish_corpus(body: HinglishSynthIn):
    """Build synthetic Hinglish WAV corpus from data/vocab CSVs via F5-TTS."""
    from engines.hinglish_vocab import vocab_stats

    stats = vocab_stats()
    if stats.get('clean_utterances', 0) == 0:
        raise HTTPException(
            status_code=422,
            detail='No clean utterances in data/vocab/hinglish_conversations.csv',
        )

    if body.dry_run:
        from training.synth_hinglish_corpus import run_synth

        return run_synth(
            max_rows=body.max_rows,
            voice_id=body.voice_id,
            dry_run=True,
            resume=True,
        )

    job = create_job(language='hinglish', job_type='hinglish_synth')
    job.status = 'running'
    upsert_job(job)
    extra = ['--max-rows', str(body.max_rows), '--voice-id', body.voice_id]
    start_synth_job_async(job.id, extra)
    return _to_out(job)


@router.post('/hinglish/export-artifacts', dependencies=_WRITE_DEPS)
async def export_hinglish_vocab_artifacts():
    """Generate normalize map, Whisper prompt, and particle list under data/vocab/."""
    from training.export_vocab_artifacts import export_artifacts

    return export_artifacts()

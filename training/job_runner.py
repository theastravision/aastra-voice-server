"""Training job persistence and background runner."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import TRAINING_JOBS_PATH

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_running: set[str] = set()


@dataclass
class TrainingJob:
    id: str
    language: str
    status: str = 'queued'
    job_type: str = 'whisper_finetune'
    sample_count: int = 0
    hours: float = 0.0
    rows_synthesized: int = 0
    error: str | None = None
    whisper_path: str | None = None
    manifest_path: str | None = None
    register_voice: bool = False
    voice_name: str | None = None
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _jobs_path() -> Path:
    return Path(TRAINING_JOBS_PATH)


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        'w', encoding='utf-8', delete=False, dir=path.parent, suffix='.tmp'
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = tmp.name
    Path(tmp_path).replace(path)


def load_jobs() -> list[TrainingJob]:
    path = _jobs_path()
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding='utf-8'))
    jobs: list[TrainingJob] = []
    for j in raw.get('jobs', []):
        j.setdefault('job_type', 'whisper_finetune')
        j.setdefault('rows_synthesized', 0)
        j.setdefault('manifest_path', None)
        jobs.append(TrainingJob(**j))
    return jobs


def save_jobs(jobs: list[TrainingJob]) -> None:
    _write_atomic(_jobs_path(), {'jobs': [asdict(j) for j in jobs]})


def get_job(job_id: str) -> TrainingJob | None:
    for j in load_jobs():
        if j.id == job_id:
            return j
    return None


def upsert_job(job: TrainingJob) -> None:
    jobs = load_jobs()
    job.updated_at = _now()
    for i, j in enumerate(jobs):
        if j.id == job.id:
            jobs[i] = job
            save_jobs(jobs)
            return
    jobs.append(job)
    save_jobs(jobs)


def create_job(
    *,
    language: str,
    job_type: str = 'whisper_finetune',
    register_voice: bool = False,
    voice_name: str | None = None,
) -> TrainingJob:
    job = TrainingJob(
        id=str(uuid.uuid4()),
        language=language,
        job_type=job_type,
        register_voice=register_voice,
        voice_name=voice_name,
    )
    upsert_job(job)
    return job


def _run_synth_subprocess(job_id: str, extra_args: list[str] | None = None) -> None:
    root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        str(root / 'training' / 'synth_hinglish_corpus.py'),
        '--job-id',
        job_id,
    ]
    if extra_args:
        cmd.extend(extra_args)
    logger.info('Starting Hinglish synth subprocess: %s', ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    if proc.returncode != 0:
        job = get_job(job_id)
        if job:
            job.status = 'failed'
            job.error = (proc.stderr or proc.stdout or 'synth failed')[:2000]
            upsert_job(job)
        logger.error('Hinglish synth job %s failed: %s', job_id, proc.stderr)


def start_synth_job_async(job_id: str, extra_args: list[str] | None = None) -> None:
    with _lock:
        if job_id in _running:
            return
        _running.add(job_id)

    def _worker() -> None:
        try:
            _run_synth_subprocess(job_id, extra_args)
        finally:
            with _lock:
                _running.discard(job_id)

    threading.Thread(target=_worker, name=f'synth-{job_id[:8]}', daemon=True).start()


def _run_job_subprocess(job_id: str, extra_args: list[str] | None = None) -> None:
    root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        str(root / 'training' / 'run_whisper_finetune.py'),
        '--job-id',
        job_id,
    ]
    if extra_args:
        cmd.extend(extra_args)
    logger.info('Starting training subprocess: %s', ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    if proc.returncode != 0:
        job = get_job(job_id)
        if job:
            job.status = 'failed'
            job.error = (proc.stderr or proc.stdout or 'training failed')[:2000]
            upsert_job(job)
        logger.error('Training job %s failed: %s', job_id, proc.stderr)


def start_job_async(job_id: str, extra_args: list[str] | None = None) -> None:
    with _lock:
        if job_id in _running:
            return
        _running.add(job_id)

    def _worker() -> None:
        try:
            _run_job_subprocess(job_id, extra_args)
        finally:
            with _lock:
                _running.discard(job_id)

    threading.Thread(target=_worker, name=f'train-{job_id[:8]}', daemon=True).start()

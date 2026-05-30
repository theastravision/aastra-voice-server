"""Import Kokoro-format dataset into STT corpus + optional TTS voice profile."""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import wave
from pathlib import Path

from engines.voice_registry import save_voice, slugify, voice_assets_dir
from training.job_runner import create_job, start_job_async
from training.prep_whisper_corpus import ingest_directory

logger = logging.getLogger(__name__)

MIN_REF_SEC = 5.0
MAX_REF_SEC = 10.0


def _score_clip(wav_path: Path, text: str) -> float:
    try:
        with wave.open(str(wav_path), 'rb') as wf:
            dur = wf.getnframes() / max(wf.getframerate(), 1)
            if dur < MIN_REF_SEC or dur > MAX_REF_SEC:
                return -1.0
            if len(text.strip()) < 10:
                return -1.0
            # Prefer mid-length clips with more text
            return dur * 0.5 + min(len(text), 120) * 0.05
    except Exception:
        return -1.0


def _pick_best_ref(input_dir: Path, metadata_csv: Path) -> tuple[Path, str] | None:
    wav_dir = input_dir / 'wavs'
    if not wav_dir.is_dir():
        wav_dir = input_dir
    rows: list[tuple[str, str]] = []
    if metadata_csv.is_file():
        with metadata_csv.open(encoding='utf-8') as f:
            for row in csv.reader(f, delimiter='|'):
                if len(row) >= 2:
                    rows.append((row[0].strip(), row[1].strip()))
    best: tuple[Path, str, float] | None = None
    for fname, text in rows:
        candidates = [
            wav_dir / fname,
            wav_dir / Path(fname).name,
            input_dir / fname,
        ]
        for p in candidates:
            if p.is_file():
                score = _score_clip(p, text)
                if score >= 0 and (best is None or score > best[2]):
                    best = (p, text, score)
                break
    if best:
        return best[0], best[1]
    for p in sorted(wav_dir.glob('*.wav')):
        score = _score_clip(p, p.stem)
        if score >= 0:
            return p, p.stem
    return None


def register_voice_from_dataset(
    input_dir: Path,
    *,
    voice_name: str,
    language: str,
) -> str:
    meta = input_dir / 'metadata.csv'
    picked = _pick_best_ref(input_dir, meta)
    if not picked:
        raise FileNotFoundError('No suitable 5–10 s reference clip found in dataset')
    src, ref_text = picked
    voice_id = slugify(voice_name)
    dest_dir = voice_assets_dir(voice_id)
    dest = dest_dir / 'ref.wav'
    shutil.copy2(src, dest)
    save_voice(
        voice_id=voice_id,
        display_name=voice_name,
        language=language,
        ref_audio_rel=f'assets/voices/{voice_id}/ref.wav',
        ref_text=ref_text,
        source='kokoro_import',
        set_default=False,
    )
    from engines.f5_tts_engine import get_manager

    try:
        get_manager().invalidate_voice(voice_id)
    except Exception:
        pass
    logger.info('Registered TTS voice %s from %s', voice_id, src)
    return voice_id


def import_kokoro_dataset(
    input_dir: Path,
    *,
    language: str,
    voice_name: str | None = None,
    start_whisper_job: bool = False,
) -> dict:
    meta = input_dir / 'metadata.csv'
    sample_count, total_sec = ingest_directory(
        input_dir, language, metadata_csv=meta if meta.is_file() else None
    )
    result: dict = {
        'sample_count': sample_count,
        'hours': round(total_sec / 3600, 3),
        'language': language,
    }
    if voice_name:
        result['voice_id'] = register_voice_from_dataset(
            input_dir, voice_name=voice_name, language=language
        )
    if start_whisper_job and sample_count > 0:
        job = create_job(
            language=language,
            register_voice=False,
            voice_name=voice_name,
        )
        job.sample_count = sample_count
        job.hours = result['hours']
        job.status = 'queued'
        from training.job_runner import upsert_job

        upsert_job(job)
        start_job_async(job.id)
        result['job_id'] = job.id
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description='Import Kokoro-format Hindi dataset')
    parser.add_argument('--input', required=True)
    parser.add_argument('--language', default='hi', choices=['en', 'hi', 'hinglish'])
    parser.add_argument('--voice-name', default=None)
    parser.add_argument('--start-whisper-job', action='store_true')
    args = parser.parse_args()
    out = import_kokoro_dataset(
        Path(args.input),
        language=args.language,
        voice_name=args.voice_name,
        start_whisper_job=args.start_whisper_job,
    )
    print(out)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()

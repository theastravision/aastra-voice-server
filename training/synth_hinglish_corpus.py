"""Synthesize Hinglish training audio from vocab conversation CSV via F5-TTS."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import wave
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    HINGLISH_SYNTH_MAX_ROWS,
    HINGLISH_SYNTH_VOICE_ID,
    TRAINING_DATA_ROOT,
)
from engines.f5_tts_engine import get_manager
from engines.hinglish_vocab import iter_conversation_utterances, vocab_stats
from training.prep_whisper_corpus import _resample_wav_to_16k_mono, append_manifest

logger = logging.getLogger(__name__)

LANGUAGE = 'hinglish'
STATE_FILE = 'synth_state.json'
F5_TEXT_FILE = 'f5_text_corpus.txt'


def _lang_dir() -> Path:
    return Path(TRAINING_DATA_ROOT) / LANGUAGE


def _wav_dir() -> Path:
    return _lang_dir() / 'wavs'


def _state_path() -> Path:
    return _lang_dir() / STATE_FILE


def _load_state() -> dict:
    path = _state_path()
    if not path.is_file():
        return {'next_index': 0, 'rows_done': 0, 'seconds': 0.0}
    return json.loads(path.read_text(encoding='utf-8'))


def _save_state(state: dict) -> None:
    _lang_dir().mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(state, indent=2), encoding='utf-8')


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), 'rb') as wf:
        return wf.getnframes() / max(wf.getframerate(), 1)


def _synthesize_to_16k_wav(text: str, dest: Path, *, voice_id: str) -> float:
    mgr = get_manager()
    mgr.set_active_voice(voice_id)
    mgr.reset_stream_state()
    wav_bytes, _mime = mgr.synthesize_wav_bytes(text)
    if not wav_bytes:
        raise ValueError('F5-TTS returned empty audio')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = Path(tmp.name)
    try:
        return _resample_wav_to_16k_mono(tmp_path, dest)
    finally:
        tmp_path.unlink(missing_ok=True)


def _append_f5_text_line(text: str) -> None:
    path = _lang_dir() / F5_TEXT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(text + '\n')


def run_synth(
    *,
    max_rows: int,
    voice_id: str,
    dry_run: bool = False,
    resume: bool = True,
) -> dict:
    utterances = iter_conversation_utterances()
    if not utterances:
        raise ValueError('No clean conversation utterances in vocab CSVs')

    state = _load_state() if resume else {'next_index': 0, 'rows_done': 0, 'seconds': 0.0}
    start_idx = int(state.get('next_index', 0))
    rows_done = int(state.get('rows_done', 0))
    seconds = float(state.get('seconds', 0.0))

    end_idx = min(len(utterances), start_idx + max_rows)
    batch = utterances[start_idx:end_idx]
    if dry_run:
        return {
            'dry_run': True,
            'utterances_available': len(utterances),
            'would_synthesize': len(batch),
            'start_index': start_idx,
            'voice_id': voice_id,
            **vocab_stats(),
        }

    _wav_dir().mkdir(parents=True, exist_ok=True)
    synthesized = 0
    for offset, text in enumerate(batch):
        idx = start_idx + offset
        wav_name = f'hinglish_{idx:06d}.wav'
        wav_path = _wav_dir() / wav_name
        if wav_path.is_file():
            dur = _wav_duration(wav_path)
        else:
            try:
                dur = _synthesize_to_16k_wav(text, wav_path, voice_id=voice_id)
            except Exception as exc:
                logger.warning('Skip utterance %d: %s', idx, exc)
                continue
            append_manifest(LANGUAGE, wav_path, text)
            _append_f5_text_line(text)
        synthesized += 1
        rows_done += 1
        seconds += dur
        state = {
            'next_index': idx + 1,
            'rows_done': rows_done,
            'seconds': round(seconds, 2),
        }
        _save_state(state)
        if synthesized % 25 == 0:
            logger.info(
                'Synth progress: %d clips, %.1f min',
                rows_done,
                seconds / 60.0,
            )

    manifest = _lang_dir() / 'manifest.tsv'
    return {
        'rows_synthesized': synthesized,
        'total_rows_done': rows_done,
        'hours': round(seconds / 3600.0, 3),
        'manifest_path': str(manifest),
        'f5_text_corpus': str(_lang_dir() / F5_TEXT_FILE),
        'next_index': state.get('next_index', end_idx),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Synthesize Hinglish STT corpus from vocab CSVs')
    parser.add_argument('--max-rows', type=int, default=HINGLISH_SYNTH_MAX_ROWS)
    parser.add_argument('--voice-id', default=HINGLISH_SYNTH_VOICE_ID)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-resume', action='store_true')
    parser.add_argument('--job-id', default=None, help='Update training job status if set')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    try:
        result = run_synth(
            max_rows=args.max_rows,
            voice_id=args.voice_id,
            dry_run=args.dry_run,
            resume=not args.no_resume,
        )
    except Exception as exc:
        if args.job_id:
            from training.job_runner import get_job, upsert_job

            job = get_job(args.job_id)
            if job:
                job.status = 'failed'
                job.error = str(exc)[:2000]
                upsert_job(job)
        raise

    if args.job_id and not args.dry_run:
        from training.job_runner import get_job, upsert_job

        job = get_job(args.job_id)
        if job:
            job.status = 'completed'
            job.sample_count = int(result.get('total_rows_done', 0))
            job.hours = float(result.get('hours', 0.0))
            job.manifest_path = result.get('manifest_path')
            job.rows_synthesized = int(result.get('rows_synthesized', 0))
            upsert_job(job)

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

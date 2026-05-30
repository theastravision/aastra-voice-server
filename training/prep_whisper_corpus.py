"""Prepare 16 kHz mono Whisper training corpus from uploads or imports."""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import struct
import sys
import wave
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import TRAINING_DATA_ROOT, WHISPER_MODEL
from engines.audio_convert import bytes_to_wav_path

logger = logging.getLogger(__name__)

SUPPORTED = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.webm'}


def _resample_wav_to_16k_mono(src: Path, dest: Path) -> float:
    """Return duration in seconds."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == '.wav':
        try:
            with wave.open(str(src), 'rb') as wf:
                if wf.getframerate() == 16000 and wf.getnchannels() == 1:
                    shutil.copy2(src, dest)
                    return wf.getnframes() / 16000.0
        except Exception:
            pass
    tmp = bytes_to_wav_path(src.read_bytes(), suffix=src.suffix)
    try:
        from pydub import AudioSegment

        seg = AudioSegment.from_wav(tmp)
        seg = seg.set_frame_rate(16000).set_channels(1)
        seg.export(str(dest), format='wav')
        return len(seg) / 1000.0
    finally:
        Path(tmp).unlink(missing_ok=True)


def _transcribe(path: Path, language: str | None) -> str:
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device='cpu', compute_type='int8')
    lang = None if language in (None, 'auto', 'hinglish') else language
    kwargs = {'beam_size': 1, 'vad_filter': False}
    if lang:
        kwargs['language'] = lang
    segments, _ = model.transcribe(str(path), **kwargs)
    return ''.join(s.text for s in segments).strip()


def append_manifest(
    language: str,
    wav_path: Path,
    transcript: str,
    *,
    rel_root: Path | None = None,
) -> None:
    lang_dir = Path(TRAINING_DATA_ROOT) / language
    lang_dir.mkdir(parents=True, exist_ok=True)
    manifest = lang_dir / 'manifest.tsv'
    root = rel_root or Path(TRAINING_DATA_ROOT)
    rel = wav_path.resolve().relative_to(root.resolve())
    with manifest.open('a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow([str(rel).replace('\\', '/'), transcript, language])


def ingest_file(
    src: Path,
    language: str,
    *,
    transcript: str | None = None,
    dest_name: str | None = None,
) -> tuple[Path, str, float]:
    lang_raw = Path(TRAINING_DATA_ROOT) / language / 'raw'
    lang_raw.mkdir(parents=True, exist_ok=True)
    name = dest_name or f'{src.stem}_{src.suffix.lstrip(".")}.wav'
    if not name.endswith('.wav'):
        name = f'{name}.wav'
    dest = lang_raw / name
    duration = _resample_wav_to_16k_mono(src, dest)
    text = (transcript or '').strip()
    if not text:
        text = _transcribe(dest, language)
    if not text:
        dest.unlink(missing_ok=True)
        raise ValueError(f'No transcript for {src.name}')
    append_manifest(language, dest, text)
    return dest, text, duration


def ingest_directory(
    input_dir: Path,
    language: str,
    *,
    metadata_csv: Path | None = None,
) -> tuple[int, float]:
    """Ingest audio files; optional metadata.csv with wav|text|phonemes."""
    transcripts: dict[str, str] = {}
    if metadata_csv and metadata_csv.is_file():
        with metadata_csv.open(encoding='utf-8') as f:
            for row in csv.reader(f, delimiter='|'):
                if len(row) >= 2:
                    key = Path(row[0].strip()).name
                    transcripts[key] = row[1].strip()

    count = 0
    total_sec = 0.0
    wav_dir = input_dir / 'wavs'
    search_roots = [wav_dir] if wav_dir.is_dir() else [input_dir]
    for root in search_roots:
        for src in sorted(root.iterdir()):
            if src.suffix.lower() not in SUPPORTED:
                continue
            text = transcripts.get(src.name)
            dest, _text, dur = ingest_file(src, language, transcript=text)
            count += 1
            total_sec += dur
            logger.info('Ingested %s -> %s (%.1fs)', src.name, dest.name, dur)
    return count, total_sec


def main() -> None:
    parser = argparse.ArgumentParser(description='Prepare Whisper STT corpus')
    parser.add_argument('--input', required=True, help='Folder with wav/mp3 or kokoro layout')
    parser.add_argument('--language', required=True, choices=['en', 'hi', 'hinglish'])
    args = parser.parse_args()
    inp = Path(args.input)
    meta = inp / 'metadata.csv'
    n, hours = ingest_directory(inp, args.language, metadata_csv=meta if meta.is_file() else None)
    print(f'Ingested {n} clips, {hours / 3600:.2f} hours -> {TRAINING_DATA_ROOT}/{args.language}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()

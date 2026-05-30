#!/usr/bin/env python3
"""Pregenerate Edge TTS audio for each interview name (one file per name)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.name_samples import NAME_SAMPLES_DIR, name_sample_path
from engines.stt_names import load_interview_names

DEFAULT_VOICE = 'en-IN-NeerjaNeural'


async def _generate_one(dest: Path, text: str, voice: str) -> None:
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice).save(str(dest))


async def _run(names: list[str], voice: str, *, skip_existing: bool, delay_ms: int) -> None:
    total = len(names)
    ok = 0
    skipped = 0
    failed = 0

    for idx, name in enumerate(names, start=1):
        dest = name_sample_path(name)
        if skip_existing and dest.is_file():
            skipped += 1
            print(f'[{idx}/{total}] skip {name} -> {dest.name}')
            continue
        print(f'[{idx}/{total}] {name} ({voice}) -> {dest.name}')
        try:
            await _generate_one(dest, name, voice)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f'  ERROR: {exc}', file=sys.stderr)
        if delay_ms > 0 and idx < total:
            await asyncio.sleep(delay_ms / 1000.0)

    print(f'Done: generated={ok} skipped={skipped} failed={failed} dir={NAME_SAMPLES_DIR}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate interview name TTS samples with edge-tts.')
    parser.add_argument('--voice', default=DEFAULT_VOICE, help=f'Edge TTS voice (default: {DEFAULT_VOICE})')
    parser.add_argument('--skip-existing', action='store_true', help='Skip names that already have mp3 files')
    parser.add_argument('--delay-ms', type=int, default=250, help='Pause between requests (default: 250)')
    parser.add_argument('--limit', type=int, default=0, help='Only process first N names (0 = all)')
    args = parser.parse_args()

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print('edge-tts is required: pip install edge-tts', file=sys.stderr)
        raise SystemExit(1) from None

    names = list(load_interview_names())
    if args.limit > 0:
        names = names[: args.limit]
    if not names:
        print('No interview names found.', file=sys.stderr)
        raise SystemExit(1)

    asyncio.run(
        _run(
            names,
            args.voice.strip(),
            skip_existing=args.skip_existing,
            delay_ms=max(0, args.delay_ms),
        )
    )


if __name__ == '__main__':
    main()

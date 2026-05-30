#!/usr/bin/env python3
"""Pregenerate Edge TTS sample audio for each Microsoft neural voice (one by one)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.name_samples import EDGE_VOICES_CATALOG, VOICE_SAMPLES_DIR, voice_sample_path

DEFAULT_SAMPLE_TEXT = 'Hello Aashish, welcome to your technical interview.'


async def _generate_one(dest: Path, text: str, voice: str) -> None:
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice).save(str(dest))


async def _run(
    voices: list[dict],
    sample_text: str,
    *,
    skip_existing: bool,
    delay_ms: int,
) -> None:
    total = len(voices)
    ok = 0
    skipped = 0
    failed = 0

    for idx, voice in enumerate(voices, start=1):
        short_name = str(voice.get('ShortName') or '').strip()
        if not short_name:
            continue
        dest = voice_sample_path(short_name)
        if skip_existing and dest.is_file():
            skipped += 1
            print(f'[{idx}/{total}] skip {short_name}')
            continue
        print(f'[{idx}/{total}] {short_name} -> {dest.name}')
        try:
            await _generate_one(dest, sample_text, short_name)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f'  ERROR: {exc}', file=sys.stderr)
        if delay_ms > 0 and idx < total:
            await asyncio.sleep(delay_ms / 1000.0)

    print(f'Done: generated={ok} skipped={skipped} failed={failed} dir={VOICE_SAMPLES_DIR}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate Edge TTS voice preview samples one by one.')
    parser.add_argument('--text', default=DEFAULT_SAMPLE_TEXT, help='Sample phrase for every voice')
    parser.add_argument('--voice', default='', help='Generate only this ShortName (e.g. en-IN-NeerjaNeural)')
    parser.add_argument('--skip-existing', action='store_true', help='Skip voices that already have mp3 files')
    parser.add_argument('--delay-ms', type=int, default=350, help='Pause between requests (default: 350)')
    parser.add_argument('--limit', type=int, default=0, help='Only process first N voices (0 = all)')
    parser.add_argument('--no-catalog', action='store_true', help='Do not write data/edge_voices.json')
    args = parser.parse_args()

    try:
        import edge_tts
    except ImportError:
        print('edge-tts is required: pip install edge-tts', file=sys.stderr)
        raise SystemExit(1) from None

    async def _main_async() -> None:
        voices = await edge_tts.list_voices()
        if not args.no_catalog:
            EDGE_VOICES_CATALOG.parent.mkdir(parents=True, exist_ok=True)
            EDGE_VOICES_CATALOG.write_text(
                json.dumps(voices, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            print(f'Wrote catalog: {EDGE_VOICES_CATALOG} ({len(voices)} voices)')

        only = args.voice.strip()
        if only:
            voices = [v for v in voices if v.get('ShortName') == only]
            if not voices:
                print(f'Voice not found: {only}', file=sys.stderr)
                raise SystemExit(1)
        if args.limit > 0:
            voices = voices[: args.limit]

        await _run(
            voices,
            args.text.strip() or DEFAULT_SAMPLE_TEXT,
            skip_existing=args.skip_existing,
            delay_ms=max(0, args.delay_ms),
        )

    asyncio.run(_main_async())


if __name__ == '__main__':
    main()

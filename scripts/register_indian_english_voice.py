#!/usr/bin/env python3
"""Register an Indian English F5-TTS voice from a 5–10 s reference WAV + transcript."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engines.voice_registry import save_voice, slugify, voice_assets_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wav', required=True, help='Reference WAV (5–10 s, clean mono)')
    parser.add_argument('--text', required=True, help='Exact transcript of the reference clip')
    parser.add_argument('--name', default='Priya', help='Display name (default: Priya)')
    parser.add_argument('--set-default', action='store_true', help='Make this the default voice')
    args = parser.parse_args()

    src = Path(args.wav).resolve()
    if not src.is_file():
        raise SystemExit(f'WAV not found: {src}')

    voice_id = slugify(args.name)
    dest_dir = voice_assets_dir(voice_id)
    dest = dest_dir / 'ref.wav'
    shutil.copy2(src, dest)

    profile = save_voice(
        voice_id=voice_id,
        display_name=args.name,
        language='en-in',
        ref_audio_rel=f'assets/voices/{voice_id}/ref.wav',
        ref_text=args.text.strip(),
        source='register_script',
        set_default=args.set_default,
    )

    try:
        from engines.f5_tts_engine import get_manager

        get_manager().invalidate_voice(voice_id)
    except Exception:
        pass

    print(f'Registered Indian English voice: {profile.id} ({profile.display_name})')
    print(f'  ref: {dest}')
    print('Restart the server, pick this voice in /interview, or set language to English.')


if __name__ == '__main__':
    main()

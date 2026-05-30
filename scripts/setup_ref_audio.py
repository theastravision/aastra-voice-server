#!/usr/bin/env python3
"""Generate Astra F5 reference audio (do not use F5's bundled 'mother nature' demo clip)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEST_DIR = ROOT / 'assets' / 'voices'
DEFAULT_DEST = DEST_DIR / 'astra_ref.wav'
HINGLISH_DEST = DEST_DIR / 'astra_ref_hinglish.wav'

_LEGACY_REF_MARKERS = ('silent spectator', 'mother nature', 'some call me nature')

try:
    from config import (
        ASTRA_DEFAULT_REF_TEXT,
        ASTRA_EDGE_TTS_VOICE,
        ASTRA_HINGLISH_BILINGUAL_REF_TEXT,
        ASTRA_HINGLISH_BILINGUAL_REF_TEXT_DEVANAGARI,
    )
except ImportError:
    ASTRA_DEFAULT_REF_TEXT = (
        'Hello, I am Astra. I will conduct your technical interview today.'
    )
    ASTRA_EDGE_TTS_VOICE = 'en-IN-NeerjaNeural'
    ASTRA_HINGLISH_BILINGUAL_REF_TEXT = (
        'Namaste, main Astra hoon. Shuru karne se pehle, screen share on rakhein. '
        'I will conduct your technical interview today. Kripya apna naam batayiye.'
    )
    ASTRA_HINGLISH_BILINGUAL_REF_TEXT_DEVANAGARI = (
        'नमस्ते, मैं Astra हूँ। शुरू करने से पहले, screen share on रखें। '
        'I will conduct your technical interview today. कृपया अपना naam बताइए।'
    )


async def _generate_with_edge_tts(dest: Path, text: str, voice: str) -> None:
    import edge_tts

    tmp = dest.with_suffix('.mp3')
    await edge_tts.Communicate(text, voice).save(str(tmp))
    try:
        import torch
        import torchaudio

        wav, sr = torchaudio.load(str(tmp))
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        target_sr = 24000
        if sr != target_sr:
            wav = torchaudio.functional.resample(wav, sr, target_sr)
        torchaudio.save(str(dest), wav, target_sr)
    finally:
        tmp.unlink(missing_ok=True)


def _text_has_legacy_ref(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _LEGACY_REF_MARKERS)


def _registry_has_legacy_text() -> bool:
    reg_path = ROOT / 'data' / 'voices.json'
    if not reg_path.is_file():
        return False
    return _text_has_legacy_ref(reg_path.read_text(encoding='utf-8'))


def _env_has_legacy_text() -> bool:
    env_path = ROOT / '.env'
    if not env_path.is_file():
        return False
    return _text_has_legacy_ref(env_path.read_text(encoding='utf-8'))


def _upsert_voice_profile(
    *,
    voice_id: str,
    display_name: str,
    language: str,
    ref_audio_rel: str,
    ref_text: str,
    source: str,
) -> None:
    reg_path = ROOT / 'data' / 'voices.json'
    if reg_path.is_file():
        data = json.loads(reg_path.read_text(encoding='utf-8'))
    else:
        data = {'default_voice_id': 'astra', 'voices': []}

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    voices = data.setdefault('voices', [])
    updated = False
    for v in voices:
        if v.get('id') == voice_id:
            v.update(
                {
                    'display_name': display_name,
                    'language': language,
                    'ref_audio': ref_audio_rel,
                    'ref_text': ref_text,
                    'source': source,
                }
            )
            updated = True
            break
    if not updated:
        voices.append(
            {
                'id': voice_id,
                'display_name': display_name,
                'language': language,
                'ref_audio': ref_audio_rel,
                'ref_text': ref_text,
                'source': source,
                'created_at': now,
            }
        )
    reg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Updated voice profile {voice_id} in {reg_path}')


def _sync_astra_default(ref_text: str) -> None:
    _upsert_voice_profile(
        voice_id='astra',
        display_name='Astra (Neerja / Indian English)',
        language='en-in',
        ref_audio_rel='assets/voices/astra_ref.wav',
        ref_text=ref_text,
        source='edge-tts-neerja',
    )


def _sync_astra_hinglish(ref_text: str) -> None:
    _upsert_voice_profile(
        voice_id='astra_hinglish',
        display_name='Astra (Hinglish bilingual ref)',
        language='hinglish',
        ref_audio_rel='assets/voices/astra_ref_hinglish.wav',
        ref_text=ref_text,
        source='edge-tts-neerja-bilingual',
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--force',
        action='store_true',
        help='Replace existing reference WAV',
    )
    parser.add_argument(
        '--hinglish-bilingual',
        action='store_true',
        help='Generate 12–14 s Hinglish+English bilingual clip (astra_ref_hinglish.wav)',
    )
    parser.add_argument(
        '--devanagari-ref-text',
        action='store_true',
        help='With --hinglish-bilingual: use mixed Devanagari ref_text in voices.json',
    )
    parser.add_argument(
        '--text',
        default=None,
        help='Transcript spoken in the generated reference clip',
    )
    parser.add_argument(
        '--voice',
        default=ASTRA_EDGE_TTS_VOICE,
        help='edge-tts voice id (default: en-IN-NeerjaNeural)',
    )
    args = parser.parse_args()

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    if args.hinglish_bilingual:
        dest = HINGLISH_DEST
        spoken_text = (args.text or ASTRA_HINGLISH_BILINGUAL_REF_TEXT).strip()
        registry_text = (
            ASTRA_HINGLISH_BILINGUAL_REF_TEXT_DEVANAGARI
            if args.devanagari_ref_text
            else spoken_text
        )
        sync_fn = lambda t: _sync_astra_hinglish(t)  # noqa: E731
    else:
        dest = DEFAULT_DEST
        spoken_text = (args.text or ASTRA_DEFAULT_REF_TEXT).strip()
        registry_text = spoken_text
        sync_fn = _sync_astra_default

    if dest.is_file() and not args.force:
        if not args.hinglish_bilingual and (_registry_has_legacy_text() or _env_has_legacy_text()):
            print(
                'Legacy F5 demo reference detected. Re-run with --force:\n'
                '  python scripts/setup_ref_audio.py --force'
            )
            raise SystemExit(1)
        print(f'Reference audio already exists: {dest}')
        print('Use --force to regenerate.')
        return

    if dest.is_file() and args.force:
        dest.unlink()

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print(
            'edge-tts is required:\n'
            '  pip install edge-tts\n'
            '  python scripts/setup_ref_audio.py --force'
        )
        raise SystemExit(1)

    print(f'Generating reference audio: {dest}')
    print(f'  spoken text: {spoken_text}')
    print(f'  registry ref_text: {registry_text}')
    print(f'  voice: {args.voice}')
    asyncio.run(_generate_with_edge_tts(dest, spoken_text, args.voice))
    sync_fn(registry_text)

    print(f'Wrote {dest}')
    if args.hinglish_bilingual:
        print('Set in .env: F5_REF_AUDIO=assets/voices/astra_ref_hinglish.wav')
        print(f'F5_REF_TEXT="{registry_text}"')
    else:
        print(f'Set in .env: F5_REF_TEXT="{registry_text}"')


if __name__ == '__main__':
    main()

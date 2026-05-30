#!/usr/bin/env python3
"""Generate F5 reference WAVs from data/voices.json (not .env or config.py)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / 'data' / 'voices.json'

_LEGACY_REF_MARKERS = ('silent spectator', 'mother nature', 'some call me nature')

# edge-tts voice per language — fixed defaults, not read from environment
_EDGE_TTS_BY_LANGUAGE: dict[str, str] = {
    'en-in': 'kn-IN-SapnaNeural',
    'en': 'kn-IN-SapnaNeural',
    'hinglish': 'hi-IN-SwaraNeural',
    'hi': 'hi-IN-SwaraNeural',
}
_DEFAULT_EDGE_TTS = 'kn-IN-SapnaNeural'


def _edge_tts_voice_for(language: str | None) -> str:
    lang = (language or '').lower().strip()
    return _EDGE_TTS_BY_LANGUAGE.get(lang, _DEFAULT_EDGE_TTS)


def _text_has_legacy_ref(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _LEGACY_REF_MARKERS)


def _load_registry() -> dict:
    if not REGISTRY_PATH.is_file():
        print(f'ERROR: Missing registry: {REGISTRY_PATH}')
        raise SystemExit(1)
    return json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))


def _registry_has_legacy_text(data: dict) -> bool:
    return _text_has_legacy_ref(json.dumps(data, ensure_ascii=False))


def _resolve_dest(ref_audio_rel: str) -> Path:
    p = Path(ref_audio_rel)
    if p.is_absolute():
        return p
    return (ROOT / p).resolve()


async def _generate_with_edge_tts(dest: Path, text: str, voice: str) -> None:
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
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


def _select_voices(data: dict, voice_ids: list[str] | None) -> list[dict]:
    voices = data.get('voices') or []
    if not voices:
        print('ERROR: voices.json has no voices[] entries')
        raise SystemExit(1)
    if not voice_ids:
        return voices
    by_id = {v['id']: v for v in voices if v.get('id')}
    missing = [vid for vid in voice_ids if vid not in by_id]
    if missing:
        print(f'ERROR: Unknown voice id(s): {", ".join(missing)}')
        raise SystemExit(1)
    return [by_id[vid] for vid in voice_ids]


def _should_generate(dest: Path, force: bool, legacy_in_registry: bool) -> bool:
    if force:
        return True
    if not dest.is_file():
        return True
    if legacy_in_registry:
        return True
    return False


async def _generate_all(
    voices: list[dict],
    *,
    force: bool,
    legacy_in_registry: bool,
    edge_voice_override: str | None,
) -> int:
    generated = 0
    for voice in voices:
        voice_id = voice.get('id') or '?'
        ref_text = (voice.get('ref_text') or '').strip()
        ref_audio_rel = voice.get('ref_audio') or ''
        if not ref_text or not ref_audio_rel:
            print(f'SKIP {voice_id}: missing ref_text or ref_audio in voices.json')
            continue

        dest = _resolve_dest(ref_audio_rel)
        if not _should_generate(dest, force, legacy_in_registry):
            print(f'OK   {voice_id}: {dest} (exists — use --force to regenerate)')
            continue

        if dest.is_file() and force:
            dest.unlink()

        edge_voice = edge_voice_override or _edge_tts_voice_for(voice.get('language'))
        print(f'GEN  {voice_id}: {dest.name}')
        print(f'     language: {voice.get("language")}')
        print(f'     edge-tts:   {edge_voice}')
        print(f'     ref_text:   {ref_text[:80]}{"…" if len(ref_text) > 80 else ""}')
        await _generate_with_edge_tts(dest, ref_text, edge_voice)
        print(f'Wrote {dest}')
        generated += 1
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate F5 reference clips for every voice in data/voices.json.',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Replace existing reference WAV files',
    )
    parser.add_argument(
        '--voice-id',
        action='append',
        dest='voice_ids',
        metavar='ID',
        help='Generate only this voice (repeatable). Default: all voices in registry',
    )
    parser.add_argument(
        '--edge-tts-voice',
        default=None,
        help='Override edge-tts voice for all generations (default: per language map)',
    )
    # Backward-compatible aliases
    parser.add_argument(
        '--hinglish-bilingual',
        action='store_true',
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    voice_ids = list(args.voice_ids or [])
    if args.hinglish_bilingual and 'astra_hinglish' not in voice_ids:
        voice_ids.append('astra_hinglish')

    data = _load_registry()
    legacy = _registry_has_legacy_text(data)
    voices = _select_voices(data, voice_ids or None)

    if legacy and not args.force:
        print(
            'Legacy F5 demo reference text detected in voices.json.\n'
            '  python scripts/setup_ref_audio.py --force'
        )
        raise SystemExit(1)

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print(
            'edge-tts is required:\n'
            '  pip install edge-tts\n'
            '  python scripts/setup_ref_audio.py'
        )
        raise SystemExit(1)

    count = asyncio.run(
        _generate_all(
            voices,
            force=args.force,
            legacy_in_registry=legacy,
            edge_voice_override=args.edge_tts_voice,
        )
    )
    if count == 0:
        print('No new reference clips generated.')
    else:
        print(f'Done — generated {count} reference clip(s). Restart the voice server.')


if __name__ == '__main__':
    main()

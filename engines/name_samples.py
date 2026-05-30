"""Interview name and Edge TTS voice sample paths for the demo UI."""

from __future__ import annotations

import json
import re
from pathlib import Path

from config import _ROOT

NAME_SAMPLES_DIR = _ROOT / 'data' / 'name-samples'
VOICE_SAMPLES_DIR = _ROOT / 'data' / 'voice-samples'
EDGE_VOICES_CATALOG = _ROOT / 'data' / 'edge_voices.json'


def name_slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-') or 'unknown'


def name_sample_path(name: str) -> Path:
    return NAME_SAMPLES_DIR / f'{name_slug(name)}.mp3'


def voice_sample_path(short_name: str) -> Path:
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', (short_name or '').strip())
    return VOICE_SAMPLES_DIR / f'{safe}.mp3'


def list_interview_name_entries() -> list[dict]:
    from engines.stt_names import load_interview_names

    entries: list[dict] = []
    for name in load_interview_names():
        path = name_sample_path(name)
        slug = name_slug(name)
        entries.append(
            {
                'name': name,
                'slug': slug,
                'has_audio': path.is_file(),
                'audio_url': f'/data/name-samples/{slug}.mp3' if path.is_file() else None,
            }
        )
    return entries


def load_edge_voice_catalog() -> list[dict]:
    if not EDGE_VOICES_CATALOG.is_file():
        return []
    try:
        data = json.loads(EDGE_VOICES_CATALOG.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    return list(data.get('voices') or [])


def list_edge_voice_entries() -> list[dict]:
    catalog = load_edge_voice_catalog()
    if not catalog:
        if VOICE_SAMPLES_DIR.is_dir():
            for path in sorted(VOICE_SAMPLES_DIR.glob('*.mp3')):
                short_name = path.stem
                catalog.append(
                    {
                        'ShortName': short_name,
                        'Gender': '',
                        'Locale': short_name.split('-')[0] if '-' in short_name else '',
                        'FriendlyName': short_name,
                    }
                )
        else:
            return []

    entries: list[dict] = []
    for voice in catalog:
        short_name = str(voice.get('ShortName') or '').strip()
        if not short_name:
            continue
        path = voice_sample_path(short_name)
        entries.append(
            {
                'short_name': short_name,
                'display_name': str(voice.get('FriendlyName') or short_name),
                'gender': str(voice.get('Gender') or ''),
                'locale': str(voice.get('Locale') or ''),
                'has_audio': path.is_file(),
                'audio_url': f'/data/voice-samples/{path.name}' if path.is_file() else None,
            }
        )
    return entries

"""Named F5-TTS voice profiles (zero-shot reference audio + transcript)."""

from __future__ import annotations

import json
import logging
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import (
    ASTRA_DEFAULT_REF_TEXT,
    VOICES_REGISTRY_PATH,
    _ROOT,
    is_legacy_f5_ref_text,
)

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r'[^a-z0-9]+')


@dataclass
class VoiceProfile:
    id: str
    display_name: str
    language: str
    ref_audio: str
    ref_text: str
    source: str = 'upload'
    speed: float | None = None
    created_at: str = field(default_factory=lambda: _now_iso())

    def ref_audio_path(self) -> Path:
        p = Path(self.ref_audio)
        if not p.is_absolute():
            p = _ROOT / p
        return p.resolve()


@dataclass
class VoiceRegistry:
    default_voice_id: str = 'astra'
    voices: list[VoiceProfile] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _registry_path() -> Path:
    return Path(VOICES_REGISTRY_PATH)


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub('-', name.lower().strip()).strip('-')
    return slug or 'voice'


def _default_registry() -> VoiceRegistry:
    return VoiceRegistry(
        default_voice_id='astra',
        voices=[
            VoiceProfile(
                id='astra',
                display_name='Astra (Sapna / Kannada)',
                language='en-in',
                ref_audio='assets/voices/astra_ref.wav',
                ref_text=ASTRA_DEFAULT_REF_TEXT,
                source='edge-tts-sapna',
            ),
        ],
    )


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        'w', encoding='utf-8', delete=False, dir=path.parent, suffix='.tmp'
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = tmp.name
    Path(tmp_path).replace(path)


def _migrate_legacy_ref_text(voices: list[VoiceProfile]) -> bool:
    """Replace F5 bundled-demo transcript on any registered voice."""
    changed = False
    for v in voices:
        if is_legacy_f5_ref_text(v.ref_text):
            logger.warning(
                'Replacing legacy F5 ref_text on voice %s with ASTRA_DEFAULT_REF_TEXT',
                v.id,
            )
            v.ref_text = ASTRA_DEFAULT_REF_TEXT
            changed = True
    return changed


def migrate_registry_legacy_refs() -> bool:
    """Load registry, migrate legacy ref_text entries, invalidate F5 cache."""
    path = _registry_path()
    if not path.is_file():
        return False
    raw = json.loads(path.read_text(encoding='utf-8'))
    voices = [VoiceProfile(**v) for v in raw.get('voices', [])]
    if not _migrate_legacy_ref_text(voices):
        return False
    save_registry(
        VoiceRegistry(
            default_voice_id=raw.get('default_voice_id') or 'astra',
            voices=voices,
        )
    )
    try:
        from engines.f5_tts_engine import invalidate_all_voice_cache

        invalidate_all_voice_cache()
    except Exception:
        logger.debug('Could not invalidate F5 voice cache after registry migration', exc_info=True)
    return True


def load_registry() -> VoiceRegistry:
    path = _registry_path()
    if not path.is_file():
        reg = _default_registry()
        save_registry(reg)
        return reg
    raw = json.loads(path.read_text(encoding='utf-8'))
    voices = [VoiceProfile(**v) for v in raw.get('voices', [])]
    if _migrate_legacy_ref_text(voices):
        save_registry(
            VoiceRegistry(
                default_voice_id=raw.get('default_voice_id') or 'astra',
                voices=voices,
            )
        )
    return VoiceRegistry(
        default_voice_id=raw.get('default_voice_id') or 'astra',
        voices=voices,
    )


def save_registry(registry: VoiceRegistry) -> None:
    payload = {
        'default_voice_id': registry.default_voice_id,
        'voices': [asdict(v) for v in registry.voices],
    }
    _write_atomic(_registry_path(), payload)


def list_voices() -> list[VoiceProfile]:
    return list(load_registry().voices)


def get_voice(voice_id: str | None) -> VoiceProfile | None:
    if not voice_id:
        reg = load_registry()
        voice_id = reg.default_voice_id
    for v in load_registry().voices:
        if v.id == voice_id:
            return v
    return None


def get_default_voice_id() -> str:
    return load_registry().default_voice_id


def save_voice(
    *,
    voice_id: str,
    display_name: str,
    language: str,
    ref_audio_rel: str,
    ref_text: str,
    source: str = 'upload',
    set_default: bool = False,
) -> VoiceProfile:
    reg = load_registry()
    profile = VoiceProfile(
        id=voice_id,
        display_name=display_name,
        language=language,
        ref_audio=ref_audio_rel,
        ref_text=ref_text,
        source=source,
    )
    if not profile.ref_audio_path().is_file():
        raise FileNotFoundError(f'Reference audio not found: {profile.ref_audio_path()}')
    if is_legacy_f5_ref_text(ref_text):
        raise ValueError(
            'Legacy F5 demo ref_text is not allowed (it bleeds into every synthesis). '
            f'Use: {ASTRA_DEFAULT_REF_TEXT!r}'
        )

    replaced = False
    for i, v in enumerate(reg.voices):
        if v.id == voice_id:
            reg.voices[i] = profile
            replaced = True
            break
    if not replaced:
        reg.voices.append(profile)
    if set_default or not reg.default_voice_id:
        reg.default_voice_id = voice_id
    save_registry(reg)
    return profile


def delete_voice(voice_id: str) -> bool:
    reg = load_registry()
    before = len(reg.voices)
    reg.voices = [v for v in reg.voices if v.id != voice_id]
    if len(reg.voices) == before:
        return False
    if reg.default_voice_id == voice_id and reg.voices:
        reg.default_voice_id = reg.voices[0].id
    save_registry(reg)
    return True


def voice_assets_dir(voice_id: str) -> Path:
    d = _ROOT / 'assets' / 'voices' / voice_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize_voice_language(code: str | None) -> str | None:
    if not code:
        return None
    c = code.lower().strip().replace('_', '-')
    if c in ('en', 'english'):
        return 'en-in'  # interview UI "English" → prefer Indian accent
    if c in ('en-in', 'en-indian', 'indian-english'):
        return 'en-in'
    if c in ('en-us', 'en-gb', 'american', 'british'):
        return c
    if c in ('hi', 'hindi'):
        return 'hi'
    if c == 'hinglish':
        return 'hinglish'
    return c


_LANG_VOICE_PRIORITY: dict[str, list[str]] = {
    'en-in': ['en-in', 'hinglish', 'hi', 'en-us', 'en'],
    'hi': ['hi', 'hinglish', 'en-in'],
    'hinglish': ['hinglish', 'en-in', 'hi', 'en-us'],
    'en-us': ['en-us', 'en-in', 'en'],
}


def resolve_voice_for_language(language_hint: str | None) -> str:
    """Pick the best registered voice for the session language."""
    reg = load_registry()
    lang = normalize_voice_language(language_hint) or 'en-in'
    prefs = _LANG_VOICE_PRIORITY.get(lang, ['en-in', 'hi', 'hinglish'])

    by_lang: dict[str, list[VoiceProfile]] = {}
    for v in reg.voices:
        key = normalize_voice_language(v.language) or v.language.lower()
        by_lang.setdefault(key, []).append(v)

    for pref in prefs:
        for v in by_lang.get(pref, []):
            if v.ref_audio_path().is_file():
                return v.id

    for v in reg.voices:
        if v.ref_audio_path().is_file():
            return v.id
    return reg.default_voice_id


def list_voices_for_language(language_hint: str | None) -> list[VoiceProfile]:
    """Voices suitable for the given UI language (ordered best-first)."""
    lang = normalize_voice_language(language_hint) or 'en-in'
    prefs = _LANG_VOICE_PRIORITY.get(lang, ['en-in'])
    reg = load_registry()
    ordered: list[VoiceProfile] = []
    seen: set[str] = set()
    by_lang: dict[str, list[VoiceProfile]] = {}
    for v in reg.voices:
        key = normalize_voice_language(v.language) or v.language.lower()
        by_lang.setdefault(key, []).append(v)
    for pref in prefs:
        for v in by_lang.get(pref, []):
            if v.id not in seen and v.ref_audio_path().is_file():
                ordered.append(v)
                seen.add(v.id)
    for v in reg.voices:
        if v.id not in seen and v.ref_audio_path().is_file():
            ordered.append(v)
            seen.add(v.id)
    return ordered

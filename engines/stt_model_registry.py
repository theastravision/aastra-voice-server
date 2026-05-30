"""Fine-tuned Whisper checkpoint registry by language."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import STT_MODELS_REGISTRY_PATH, _ROOT

logger = logging.getLogger(__name__)


@dataclass
class SttModelEntry:
    whisper_path: str
    job_id: str = ''
    ready: bool = False
    sample_count: int = 0
    hours: float = 0.0


@dataclass
class SttModelsRegistry:
    stt_by_language: dict[str, SttModelEntry] = field(default_factory=dict)


def _path() -> Path:
    return Path(STT_MODELS_REGISTRY_PATH)


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        'w', encoding='utf-8', delete=False, dir=path.parent, suffix='.tmp'
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = tmp.name
    Path(tmp_path).replace(path)


def load_models_registry() -> SttModelsRegistry:
    path = _path()
    if not path.is_file():
        reg = SttModelsRegistry()
        save_models_registry(reg)
        return reg
    raw = json.loads(path.read_text(encoding='utf-8'))
    entries = {
        lang: SttModelEntry(**entry)
        for lang, entry in raw.get('stt_by_language', {}).items()
    }
    return SttModelsRegistry(stt_by_language=entries)


def save_models_registry(registry: SttModelsRegistry) -> None:
    payload = {
        'stt_by_language': {
            lang: asdict(entry) for lang, entry in registry.stt_by_language.items()
        },
    }
    _write_atomic(_path(), payload)


def resolve_whisper_path_for_language(language: str | None) -> str | None:
    """Return CT2 folder path if a fine-tuned model is ready for this language."""
    if not language:
        return None
    lang = language.lower().strip()
    if lang == 'hinglish':
        lang = 'hi'
    reg = load_models_registry()
    entry = reg.stt_by_language.get(lang)
    if not entry or not entry.ready:
        return None
    p = Path(entry.whisper_path)
    if not p.is_absolute():
        p = _ROOT / p
    if p.is_dir():
        return str(p.resolve())
    return None


def set_stt_model(
    language: str,
    *,
    whisper_path: str,
    job_id: str,
    ready: bool,
    sample_count: int = 0,
    hours: float = 0.0,
) -> None:
    reg = load_models_registry()
    reg.stt_by_language[language] = SttModelEntry(
        whisper_path=whisper_path,
        job_id=job_id,
        ready=ready,
        sample_count=sample_count,
        hours=hours,
    )
    save_models_registry(reg)

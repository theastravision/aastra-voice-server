"""Export runtime/training artifacts from Hinglish vocab CSVs."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import HINGLISH_VOCAB_DIR
from engines.hinglish_vocab import (
    build_normalize_variant_map,
    build_whisper_vocab_prompt,
    hinglish_particles,
    vocab_stats,
)

logger = logging.getLogger(__name__)

NORMALIZE_JSON = 'hinglish_normalize.generated.json'
WHISPER_PROMPT = 'whisper_hinglish_prompt.txt'
PARTICLES_TXT = 'hinglish_particles.txt'


def export_artifacts(*, out_dir: Path | None = None, prompt_max_chars: int = 400) -> dict:
    root = out_dir or Path(HINGLISH_VOCAB_DIR)
    root.mkdir(parents=True, exist_ok=True)

    normalize_path = root / NORMALIZE_JSON
    prompt_path = root / WHISPER_PROMPT
    particles_path = root / PARTICLES_TXT

    variant_map = build_normalize_variant_map()
    prompt = build_whisper_vocab_prompt(max_chars=prompt_max_chars)
    particles = sorted(hinglish_particles())

    normalize_path.write_text(
        json.dumps(variant_map, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    prompt_path.write_text(prompt, encoding='utf-8')
    particles_path.write_text('\n'.join(particles) + '\n', encoding='utf-8')

    stats = vocab_stats()
    return {
        'normalize_map': str(normalize_path),
        'whisper_prompt': str(prompt_path),
        'particles': str(particles_path),
        'variant_count': len(variant_map),
        'particle_count': len(particles),
        'prompt_chars': len(prompt),
        **stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Export Hinglish vocab artifacts')
    parser.add_argument('--out-dir', default=HINGLISH_VOCAB_DIR)
    parser.add_argument('--prompt-max-chars', type=int, default=400)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = export_artifacts(
        out_dir=Path(args.out_dir),
        prompt_max_chars=args.prompt_max_chars,
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

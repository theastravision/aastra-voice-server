"""Merge Whisper training manifests with deduplication by normalized transcript."""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import TRAINING_DATA_ROOT
from engines.stt_filters import normalize_stt_text

logger = logging.getLogger(__name__)


def _read_manifest(path: Path, *, root: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    with path.open(encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) < 2:
                continue
            rel, text = parts[0].strip(), parts[1].strip()
            lang = parts[2].strip() if len(parts) > 2 else 'hinglish'
            if not rel or not text:
                continue
            wav = (root / rel).resolve()
            if not wav.is_file():
                logger.warning('Missing wav for manifest row: %s', rel)
                continue
            rows.append((rel.replace('\\', '/'), text, lang))
    return rows


def merge_manifests(
    *manifest_paths: Path,
    output_language: str = 'hinglish',
    output_name: str = 'manifest_merged.tsv',
) -> dict:
    root = Path(TRAINING_DATA_ROOT).resolve()
    out_dir = root / output_language
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_name

    seen: set[str] = set()
    merged: list[tuple[str, str, str]] = []
    for manifest in manifest_paths:
        if not manifest.is_file():
            logger.warning('Skip missing manifest: %s', manifest)
            continue
        manifest_root = root
        if manifest.parent.name in ('hi', 'en', 'hinglish'):
            manifest_root = root
        for rel, text, lang in _read_manifest(manifest, root=manifest_root):
            key = normalize_stt_text(text)
            if key in seen:
                continue
            seen.add(key)
            merged.append((rel, text, lang or output_language))

    with out_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        for rel, text, lang in merged:
            writer.writerow([rel, text, lang])

    return {
        'output': str(out_path),
        'rows': len(merged),
        'sources': [str(p) for p in manifest_paths if p.is_file()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Merge Whisper manifest TSV files')
    parser.add_argument(
        'manifests',
        nargs='+',
        help='Paths to manifest.tsv files (relative to TRAINING_DATA_ROOT or absolute)',
    )
    parser.add_argument('--language', default='hinglish')
    parser.add_argument('--output', default='manifest_merged.tsv')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    root = Path(TRAINING_DATA_ROOT)
    paths = []
    for raw in args.manifests:
        p = Path(raw)
        if not p.is_file():
            p = root / raw / 'manifest.tsv'
        paths.append(p)
    result = merge_manifests(*paths, output_language=args.language, output_name=args.output)
    print(result)


if __name__ == '__main__':
    main()

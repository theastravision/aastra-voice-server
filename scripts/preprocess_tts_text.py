#!/usr/bin/env python3
"""CLI for TTS text preprocessing (normalize + Devanagari transliteration)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engines.tts_text_pipeline import preprocess_debug, prepare_text_for_tts


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--text', required=True, help='Input text to preprocess')
    parser.add_argument(
        '--mode',
        choices=('roman', 'devanagari'),
        default='devanagari',
        help='Output script mode',
    )
    parser.add_argument(
        '--reply-script',
        choices=('en', 'hi', 'hinglish'),
        default='hinglish',
    )
    parser.add_argument('--json', action='store_true', help='Emit full debug JSON')
    args = parser.parse_args()

    if args.json:
        data = preprocess_debug(args.text, reply_script=args.reply_script)
        data['final'] = prepare_text_for_tts(
            args.text,
            reply_script=args.reply_script,
            output_script=args.mode,
        )
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    result = prepare_text_for_tts(
        args.text,
        reply_script=args.reply_script,
        output_script=args.mode,
    )
    print(result)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Evaluate F5 Devanagari / XTTS Hinglish synthesis quality."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOLDEN_PHRASES = [
    'Shuru karne se pehle, screen share on rakhein.',
    'Maaf kijiye, main aapka naam sun nahi payi.',
    'Welcome Rahul. Apne baare mein thoda batayiye.',
    'React use karta hoon aur backend mein Python prefer karta hoon.',
    'Kripya apna full naam boliye.',
    (
        'Phir Aashish ne decide kiya, ki woh bada hokar engineer banega. '
        'Aur aisi technology banayega, jo gaon, shehar aur desh ke logon ki zindagi aasaan bana sake.'
    ),
]

TTS_EVAL_CER_THRESHOLD = 0.45


def _synthesize(engine: str, text: str, out: Path) -> bool:
    try:
        if engine == 'xtts':
            from engines.xtts_engine import get_manager, xtts_available

            if not xtts_available():
                return False
            mgr = get_manager()
            wav_bytes, _ = mgr.synthesize_wav_bytes(text, reply_script='hinglish')
        else:
            from engines.f5_tts_engine import f5_available, get_manager

            if not f5_available():
                return False
            mgr = get_manager()
            wav_bytes, _ = mgr.synthesize_wav_bytes(text, reply_script='hinglish')
        if not wav_bytes:
            return False
        out.write_bytes(wav_bytes)
        return True
    except Exception as exc:
        print(f'  synth failed: {exc}')
        return False


def _whisper_cer(reference: str, wav_path: Path) -> float | None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    try:
        model = WhisperModel('base', device='cpu', compute_type='int8')
        segments, _ = model.transcribe(str(wav_path), language='hi')
        hyp = ' '.join(s.text.strip() for s in segments).lower()
        ref = reference.lower()
        if not ref:
            return None
        # Simple word-error proxy
        ref_words = ref.split()
        hyp_words = hyp.split()
        if not ref_words:
            return None
        matches = sum(1 for w in ref_words if w in hyp_words)
        return 1.0 - (matches / len(ref_words))
    except Exception as exc:
        print(f'  whisper eval skipped: {exc}')
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--engine',
        choices=('f5', 'xtts', 'both'),
        default='both',
    )
    parser.add_argument('--out-dir', default='data/eval/tts_hinglish')
    parser.add_argument('--whisper-cer', action='store_true')
    args = parser.parse_args()

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    engines = ['f5', 'xtts'] if args.engine == 'both' else [args.engine]
    summary: dict[str, object] = {'engines': {}, 'recommend_fallback': False}

    for engine in engines:
        engine_dir = out_root / engine
        engine_dir.mkdir(parents=True, exist_ok=True)
        rows: list[dict] = []
        bad = 0
        for i, phrase in enumerate(GOLDEN_PHRASES):
            from engines.tts_text_pipeline import preprocess_debug

            debug = preprocess_debug(phrase, reply_script='hinglish')
            wav_path = engine_dir / f'phrase_{i + 1:02d}.wav'
            ok = _synthesize(engine, phrase, wav_path)
            cer = _whisper_cer(phrase, wav_path) if ok and args.whisper_cer else None
            if cer is not None and cer > TTS_EVAL_CER_THRESHOLD:
                bad += 1
            rows.append(
                {
                    'phrase': phrase,
                    'devanagari': debug.get('devanagari'),
                    'wav': str(wav_path),
                    'synthesized': ok,
                    'cer': cer,
                }
            )
        summary['engines'][engine] = {
            'phrases': rows,
            'high_cer_count': bad,
        }
        if engine == 'f5' and bad >= 2:
            summary['recommend_fallback'] = True

    report = out_root / 'report.json'
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'Wrote {report}')
    if summary.get('recommend_fallback'):
        print('Recommendation: set TTS_HINGLISH_ENGINE=xtts in .env')


if __name__ == '__main__':
    main()

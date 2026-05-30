"""Tests for vocab export and manifest merge."""

import csv
import tempfile
from pathlib import Path

from training.export_vocab_artifacts import export_artifacts
from training.merge_manifests import merge_manifests


def test_export_vocab_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = export_artifacts(out_dir=out)
        assert result['variant_count'] > 0
        assert result['particle_count'] > 0
        assert (out / 'whisper_hinglish_prompt.txt').is_file()
        assert (out / 'hinglish_particles.txt').is_file()
        assert (out / 'hinglish_normalize.generated.json').is_file()


def test_merge_manifests_dedupes(tmp_path, monkeypatch):
    root = tmp_path / 'training'
    hi_dir = root / 'hi'
    hinglish_dir = root / 'hinglish'
    hi_wavs = hi_dir / 'wavs'
    hinglish_wavs = hinglish_dir / 'wavs'
    hi_wavs.mkdir(parents=True)
    hinglish_wavs.mkdir(parents=True)

    wav1 = hi_wavs / 'a.wav'
    wav2 = hinglish_wavs / 'b.wav'
    wav1.write_bytes(b'RIFF')
    wav2.write_bytes(b'RIFF')

    with (hi_dir / 'manifest.tsv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['hi/wavs/a.wav', 'Mera naam Rahul hai', 'hi'])

    with (hinglish_dir / 'manifest.tsv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['hinglish/wavs/b.wav', 'Mera naam Rahul hai', 'hinglish'])
        writer.writerow(['hinglish/wavs/b.wav', 'Main software engineer hoon', 'hinglish'])

    monkeypatch.setenv('TRAINING_DATA_ROOT', str(root))
    from importlib import reload
    import config
    import training.merge_manifests as merge_mod

    reload(config)
    reload(merge_mod)

    result = merge_mod.merge_manifests(
        hi_dir / 'manifest.tsv',
        hinglish_dir / 'manifest.tsv',
    )
    assert result['rows'] == 2
    merged = (hinglish_dir / 'manifest_merged.tsv').read_text(encoding='utf-8')
    assert 'software engineer' in merged
    assert merged.count('Mera naam Rahul hai') == 1

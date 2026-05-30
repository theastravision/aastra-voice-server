"""Tests for language-aware interjection selection."""

from engines.interjections import pick_interjection


def test_pick_interjection_disabled_for_english():
    assert pick_interjection('en') is None


def test_pick_interjection_hi_only_hindi_fillers(monkeypatch):
    from engines import interjections

    clips = [
        interjections.CachedInterjection('Hmm...', b'\x00\x00', 24000, 'en'),
        interjections.CachedInterjection('Achha...', b'\x00\x00', 24000, 'hi'),
    ]
    monkeypatch.setattr(interjections, '_cache', clips)
    picked = pick_interjection('hi')
    assert picked is not None
    assert picked.reply_script == 'hi'

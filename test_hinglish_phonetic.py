"""Tests for Hinglish phonetic transforms (disabled by default)."""

import os

from engines.hinglish_phonetic import (
    apply_phonetic_hyphens,
    denormalize_phonetic_text,
)
from engines.tts_text_pipeline import prepare_text_for_tts

AASHISH_STORY = (
    'Phir Aashish ne decide kiya, ki woh bada hokar engineer banega. '
    'Aur aisi technology banayega, jo gaon, shehar aur desh ke logon ki zindagi aasaan bana sake.'
)


def test_phonetic_disabled_by_default():
    text = 'Phir Aashish ne decide kiya, technology engineer banega.'
    assert apply_phonetic_hyphens(text, reply_script='hinglish') == text


def test_phonetic_english_session_unchanged():
    text = 'Tell me about your technology experience.'
    assert apply_phonetic_hyphens(text, reply_script='en') == text


def test_phonetic_static_glossary_when_enabled(monkeypatch):
    monkeypatch.setenv('TTS_HINGLISH_PHONETIC_HYPHEN', 'true')
    from importlib import reload

    import config
    import engines.hinglish_phonetic as phonetic_mod

    reload(config)
    reload(phonetic_mod)

    assert phonetic_mod.apply_phonetic_hyphens('technology', reply_script='hinglish') == 'tek-no-lo-jee'
    assert phonetic_mod.apply_phonetic_hyphens('Engineer', reply_script='hinglish') == 'In-jin-eer'


def test_stt_denorm_disabled_by_default():
    text = 'tek no lo jee stack'
    assert denormalize_phonetic_text(text, reply_script='hinglish') == text


def test_stt_denorm_when_enabled(monkeypatch):
    monkeypatch.setenv('STT_HINGLISH_PHONETIC_DENORM', 'true')
    from importlib import reload

    import config
    import engines.hinglish_phonetic as phonetic_mod

    reload(config)
    reload(phonetic_mod)

    assert phonetic_mod.denormalize_phonetic_text('tek-no-lo-jee stack', reply_script='hinglish') == 'technology stack'


def test_full_story_pipeline_uses_pacing_not_phonetic():
    result = prepare_text_for_tts(AASHISH_STORY, reply_script='hinglish')
    assert 'technology' in result
    assert 'engineer' in result
    assert 'dee-sa-eed' not in result
    assert 'tek no lo jee' not in result
    assert result.count('...') >= 4

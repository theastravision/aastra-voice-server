"""Tests for Hinglish TTS pacing pauses."""

import os

from engines.tts_pacing import add_speech_pauses


def test_story_comma_becomes_ellipsis_pause(monkeypatch):
    monkeypatch.setenv('TTS_HINGLISH_PAUSE_STYLE', 'story')
    from importlib import reload

    import config
    import engines.tts_pacing as pacing_mod

    reload(config)
    reload(pacing_mod)

    text = 'Phir Aashish ne decide kiya, ki woh engineer banega.'
    result = pacing_mod.add_speech_pauses(text, reply_script='hinglish')
    assert ', ...' not in result
    assert 'kiya ... ki' in result


def test_story_place_list_pauses(monkeypatch):
    monkeypatch.setenv('TTS_HINGLISH_PAUSE_STYLE', 'story')
    from importlib import reload

    import config
    import engines.tts_pacing as pacing_mod

    reload(config)
    reload(pacing_mod)

    text = 'jo gaon, shehar aur desh ke logon ki'
    result = pacing_mod.add_speech_pauses(text, reply_script='hinglish')
    assert 'gaon ... shehar' in result or 'gaon ... she-har' in result
    assert '... aur desh' in result


def test_standard_comma_gets_ellipsis_pause(monkeypatch):
    monkeypatch.setenv('TTS_HINGLISH_PAUSE_STYLE', 'standard')
    from importlib import reload

    import config
    import engines.tts_pacing as pacing_mod

    reload(config)
    reload(pacing_mod)

    text = 'Phir Aashish ne decide kiya, ki woh engineer banega.'
    result = pacing_mod.add_speech_pauses(text, reply_script='hinglish')
    assert ', ...' in result
    assert 'decide kiya, ... ki' in result


def test_mixed_script_boundary_pause(monkeypatch):
    monkeypatch.setenv('TTS_HINGLISH_PAUSE_STYLE', 'standard')
    from importlib import reload

    import config
    import engines.tts_pacing as pacing_mod

    reload(config)
    reload(pacing_mod)

    text = 'आप React use karte hain'
    result = pacing_mod.add_speech_pauses(text, reply_script='hinglish')
    assert ' ... ' in result


def test_english_unchanged():
    text = 'Tell me about your project.'
    assert add_speech_pauses(text, reply_script='en') == text

"""Tests for Hinglish TTS pacing pauses."""

from engines.tts_pacing import add_speech_pauses


def test_comma_gets_ellipsis_pause():
    text = 'Phir Aashish ne decide kiya, ki woh engineer banega.'
    result = add_speech_pauses(text, reply_script='hinglish')
    assert ', ...' in result
    assert 'decide kiya, ... ki' in result


def test_mixed_script_boundary_pause():
    text = 'आप React use karte hain'
    result = add_speech_pauses(text, reply_script='hinglish')
    assert ' ... ' in result


def test_english_unchanged():
    text = 'Tell me about your project.'
    assert add_speech_pauses(text, reply_script='en') == text

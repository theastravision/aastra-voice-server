"""Tests for TTS backend routing (F5 English, svara Indic)."""

from unittest.mock import patch


def test_english_uses_f5():
    from engines.tts_router import resolve_tts_backend

    assert resolve_tts_backend('en') == 'f5'
    assert resolve_tts_backend(None) == 'f5'


def test_hindi_uses_svara_when_available(monkeypatch):
    from engines.tts_router import resolve_tts_backend

    monkeypatch.setattr('config.TTS_INDIC_ENGINE', 'svara')
    with patch('engines.svara_tts_engine.svara_available', return_value=True):
        assert resolve_tts_backend('hi') == 'svara'
        assert resolve_tts_backend('hinglish') == 'svara'


def test_hindi_falls_back_to_f5_when_svara_missing(monkeypatch):
    from engines.tts_router import resolve_tts_backend

    monkeypatch.setattr('config.TTS_INDIC_ENGINE', 'svara')
    with patch('engines.svara_tts_engine.svara_available', return_value=False):
        assert resolve_tts_backend('hi') == 'f5'


def test_indic_lang_code_uses_svara(monkeypatch):
    from engines.tts_router import resolve_tts_backend

    monkeypatch.setattr('config.TTS_INDIC_ENGINE', 'svara')
    with patch('engines.svara_tts_engine.svara_available', return_value=True):
        assert resolve_tts_backend('ta') == 'svara'

"""Tests for TtsWorker backend selection and logging."""

import logging
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_tts_worker_start_logs_backend(caplog, monkeypatch):
    from tts_worker import TtsWorker

    monkeypatch.setattr('config.TTS_INDIC_ENGINE', 'svara')
    worker = TtsWorker()
    with patch('engines.svara_tts_engine.svara_available', return_value=True):
        with patch('engines.svara_tts_engine.get_manager') as mock_mgr:
            mock_mgr.return_value.set_active_speaker = lambda **_: None
            caplog.set_level(logging.INFO, logger='tts_worker')
            await worker.start(language_hint='hi', voice_id='astra_hinglish')

    assert worker._backend == 'svara'
    assert any('TTS backend=svara' in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_tts_worker_start_f5_for_english(caplog):
    from tts_worker import TtsWorker

    worker = TtsWorker()
    with patch('engines.f5_tts_engine.get_manager') as mock_mgr:
        mock_mgr.return_value.set_active_voice = lambda *a, **k: None
        mock_mgr.return_value.reset_stream_state = lambda: None
        caplog.set_level(logging.INFO, logger='tts_worker')
        await worker.start(language_hint='en', voice_id='astra')

    assert worker._backend == 'f5'
    assert any('TTS backend=f5' in r.message for r in caplog.records)

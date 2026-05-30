"""Tests for utterance STT accumulation and best-text merge."""

from engines.stt_filters import is_phantom_stt_text, pick_best_stt_text


def test_pick_best_prefers_long_substantive_over_garbage():
    good = (
        'My name is Azush and I have seven years of experience with Python '
        'and other programming languages.'
    )
    garbage = 'LLM.'
    assert pick_best_stt_text(garbage, good) == good
    assert pick_best_stt_text(good, garbage) == good


def test_pick_best_rejects_phantom_url():
    good = 'I have worked on LLM projects for five years in production.'
    phantom = 'www.tank.com.au'
    assert pick_best_stt_text(phantom, good) == good


def test_phantom_detects_repeated_words():
    assert is_phantom_stt_text('Terms. Terms. Terms. Terms. Terms.')


def test_phantom_detects_short_llm_token():
    assert is_phantom_stt_text('LLM.')


def test_pick_best_empty_when_all_phantom():
    assert pick_best_stt_text('LLM.', 'On.', 'And...') == ''


def test_stt_worker_flush_empty_when_buffer_too_small():
    import asyncio
    from unittest.mock import patch

    from stt_worker import SttWorker

    async def _run():
        worker = SttWorker()
        with patch('stt_worker.FasterWhisperInferenceManager.for_language'):
            await worker.start(language_hint='en')
        worker._utterance_buffer.extend(b'\x00' * 100)
        events = await worker.flush()
        assert events == []

    asyncio.run(_run())


def test_stt_worker_flush_transcribes_full_utterance():
    import asyncio
    from unittest.mock import MagicMock, patch

    from stt_worker import SttWorker

    async def _run():
        worker = SttWorker()
        with patch('stt_worker.FasterWhisperInferenceManager.for_language'):
            await worker.start(language_hint='en')
        worker._utterance_buffer.extend(b'\x00' * 32000)
        worker._manager = MagicMock()
        worker._manager.transcribe_pcm.return_value = {
            'text': 'Full good answer about Python experience.',
            'detected_language': 'en',
        }
        events = await worker.flush()

        assert len(events) == 1
        assert events[0].is_final is True
        assert 'Python experience' in events[0].text

    asyncio.run(_run())


def test_stt_worker_flush_rejects_phantom_transcript():
    import asyncio
    from unittest.mock import MagicMock, patch

    from stt_worker import SttWorker

    async def _run():
        worker = SttWorker()
        with patch('stt_worker.FasterWhisperInferenceManager.for_language'):
            await worker.start(language_hint='en')
        worker._utterance_buffer.extend(b'\x00' * 32000)
        worker._manager = MagicMock()
        worker._manager.transcribe_pcm.return_value = {
            'text': 'LLM.',
            'detected_language': 'en',
        }
        events = await worker.flush()
        assert events == []

    asyncio.run(_run())

"""Tests for svara HTTP sidecar client."""

from unittest.mock import MagicMock, patch

import httpx


def test_svara_available_on_healthy_sidecar():
    from engines import svara_tts_engine

    svara_tts_engine._sidecar_ok = False
    svara_tts_engine._availability_error = None

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch('engines.svara_tts_engine.httpx.get', return_value=mock_response):
        assert svara_tts_engine.svara_available() is True


def test_svara_available_false_on_connection_error():
    from engines import svara_tts_engine

    svara_tts_engine._sidecar_ok = False
    svara_tts_engine._availability_error = None

    with patch(
        'engines.svara_tts_engine.httpx.get',
        side_effect=httpx.ConnectError('connection refused'),
    ):
        assert svara_tts_engine.svara_available() is False
        assert 'connection refused' in (svara_tts_engine._availability_error or '')


def test_synthesize_stream_yields_pcm_chunks():
    from engines import svara_tts_engine

    pcm_chunk = b'\x00\x01' * 100
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_bytes = MagicMock(return_value=iter([pcm_chunk]))
    mock_response.raise_for_status = MagicMock()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    mgr = svara_tts_engine.SvaraTtsManager()
    with patch('engines.svara_tts_engine.httpx.Client', return_value=mock_client):
        with patch(
            'engines.svara_tts_engine.prepare_text_for_svara',
            return_value='नमस्ते',
        ):
            chunks = list(
                mgr.synthesize_stream_sync('hello', reply_script='hi', voice_id=None)
            )

    assert len(chunks) == 1
    audio, sr = chunks[0]
    assert sr == 24000
    assert len(audio) > 0
    mock_client.stream.assert_called_once()
    call_kwargs = mock_client.stream.call_args
    payload = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
    assert payload['response_format'] == 'pcm'
    assert payload['stream'] is True


def test_warmup_raises_when_sidecar_unhealthy():
    from engines import svara_tts_engine

    mgr = svara_tts_engine.SvaraTtsManager()
    with patch('engines.svara_tts_engine._check_sidecar_health', return_value=False):
        svara_tts_engine._availability_error = 'unhealthy'
        try:
            mgr.warmup()
            raised = False
        except RuntimeError as exc:
            raised = True
            assert 'unhealthy' in str(exc)
        assert raised

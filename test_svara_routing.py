"""Tests for svara sidecar availability caching and invalidation."""

import time
from unittest.mock import patch

from engines import svara_tts_engine as svara


def test_svara_available_rechecks_when_stale(monkeypatch):
    monkeypatch.setattr(svara, '_sidecar_ok', True)
    monkeypatch.setattr(svara, '_last_health_check', time.monotonic() - 60)
    calls = {'n': 0}

    def fake_check(**kwargs):
        calls['n'] += 1
        return True

    monkeypatch.setattr(svara, '_check_sidecar_health', fake_check)
    assert svara.svara_available() is True
    assert calls['n'] == 1


def test_invalidate_sidecar_cache_forces_recheck(monkeypatch):
    monkeypatch.setattr(svara, '_sidecar_ok', True)
    monkeypatch.setattr(svara, '_last_health_check', time.monotonic())
    calls = {'n': 0}

    def fake_check(**kwargs):
        calls['n'] += 1
        return False

    monkeypatch.setattr(svara, '_check_sidecar_health', fake_check)
    svara.invalidate_sidecar_cache()
    assert svara.svara_available() is False
    assert calls['n'] == 1

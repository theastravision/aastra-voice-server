"""ONNX Runtime env setup — must run before the first ``onnxruntime`` import."""

from __future__ import annotations

import os

_configured = False


def configure_ort_runtime() -> None:
    """
    Suppress harmless ORT warnings (e.g. DRM /sys/class/drm/card0 scans on headless GPU nodes).

    faster-whisper loads Silero VAD via ONNX when ``vad_filter=True``. Severity 3 = errors only.
    Override with ``ORT_LOGGING_LEVEL`` in ``.env`` if you need ORT debug output.
    """
    global _configured
    if _configured:
        return
    _configured = True
    os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
    os.environ.setdefault('ORT_LOG_SEVERITY_LEVEL', '3')

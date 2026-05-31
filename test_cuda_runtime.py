"""Tests for CUDA runtime LD_LIBRARY_PATH setup."""

from core.cuda_runtime import configure_cuda_runtime, cuda_library_dirs


def test_configure_cuda_runtime_no_crash():
    configure_cuda_runtime()


def test_cuda_library_dirs_when_nvidia_wheels_present():
    dirs = cuda_library_dirs()
    if not dirs:
        return
    configure_cuda_runtime()
    import os

    assert os.environ.get('LD_LIBRARY_PATH')

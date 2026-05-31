"""CUDA pip-wheel library paths (cuBLAS, cuDNN, NVRTC) for GPU inference."""

from __future__ import annotations

import os

_configured = False

_NVIDIA_LIB_MODULES = (
    'nvidia.cublas.lib',
    'nvidia.cudnn.lib',
    'nvidia.cuda_nvrtc.lib',
    'nvidia.cuda_runtime.lib',
    'nvidia.nccl.lib',
    'nvidia.cufft.lib',
    'nvidia.curand.lib',
    'nvidia.cusolver.lib',
    'nvidia.cusparse.lib',
)


def cuda_library_dirs() -> list[str]:
    import importlib

    dirs: list[str] = []
    seen: set[str] = set()
    for mod_name in _NVIDIA_LIB_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            path = os.path.dirname(mod.__file__)
        except ImportError:
            continue
        if path and path not in seen:
            dirs.append(path)
            seen.add(path)
    return dirs


def configure_cuda_runtime() -> None:
    """
    Extend LD_LIBRARY_PATH with NVIDIA wheels (incl. NVRTC for torchaudio/F5/vLLM).

    Must run before first CUDA JIT op (F5 mel spectrogram, vLLM, etc.).
    """
    global _configured
    if _configured:
        return
    _configured = True
    dirs = cuda_library_dirs()
    if not dirs:
        return
    prefix = os.pathsep.join(dirs)
    existing = os.environ.get('LD_LIBRARY_PATH', '')
    if prefix not in existing:
        os.environ['LD_LIBRARY_PATH'] = f'{prefix}{os.pathsep}{existing}' if existing else prefix


def cuda_library_path_export() -> str:
    """Return LD_LIBRARY_PATH string for shell scripts (run-demo.sh, Docker)."""
    configure_cuda_runtime()
    return os.environ.get('LD_LIBRARY_PATH', '')

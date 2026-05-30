# GPU voice server for Salad Cloud / CUDA hosts (RTX 3090+ class)
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    espeak-ng \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

COPY requirements.txt .
# PyTorch CUDA 12.4 wheels (install before other deps that depend on torch)
RUN pip install --upgrade pip \
    && pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124 \
    && pip install -r requirements.txt

COPY config.py auth.py main.py ./
COPY engines ./engines
COPY routers ./routers

# Salad Container Gateway requires IPv6 bind
ENV PORT=8888
EXPOSE 8888

# LD_LIBRARY_PATH for faster-whisper GPU (cuBLAS/cuDNN via pip)
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64"

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8888/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "::", "--port", "8888"]

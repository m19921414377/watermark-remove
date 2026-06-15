ARG CUDA_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
FROM ${CUDA_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HOME=/cache/huggingface \
    TORCH_HOME=/cache/torch \
    PATH="/home/appuser/.local/bin:${PATH}"

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
ARG TORCH_PACKAGES="torch torchvision"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    ffmpeg \
    git \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt ./

RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install --index-url "${TORCH_INDEX_URL}" ${TORCH_PACKAGES} \
    && python3 -m pip install -r requirements-docker.txt

COPY . .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /data/input /data/output /data/work /cache/huggingface /cache/torch \
    && chown -R appuser:appuser /app /data /cache

USER appuser

EXPOSE 7860

ENTRYPOINT ["python3", "watermark_manifest_webui.py"]
CMD ["--input", "/data/input", "--workdir", "/data/work", "--host", "0.0.0.0", "--port", "7860"]

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/cache/huggingface \
    TORCH_HOME=/cache/torch

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
ARG TORCH_PACKAGES="torch torchvision"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt ./

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --index-url "${TORCH_INDEX_URL}" ${TORCH_PACKAGES} \
    && python -m pip install -r requirements-docker.txt

COPY . .

RUN mkdir -p /data/input /data/output /data/work /cache/huggingface /cache/torch

EXPOSE 7860

ENTRYPOINT ["python", "watermark_manifest_webui.py"]
CMD ["--input", "/data/input", "--workdir", "/data/work", "--host", "0.0.0.0", "--port", "7860"]

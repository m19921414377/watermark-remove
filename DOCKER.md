# Docker and GHCR Deployment

This fork supports two container workflows:

- WebUI mask review: draw a different watermark box for each video and save `watermark-map.json`.
- GPU batch processing: read `watermark-map.json` and run LaMa per video.

## Local Docker

Put videos under:

```text
data/input/
```

Start the WebUI:

```bash
docker compose up --build
```

Open:

```text
http://localhost:7860
```

Draw one watermark box per video, then save. The manifest is written to:

```text
data/work/watermark-map.json
```

## Batch Processing in the Container

After the manifest is ready:

```bash
docker compose run --rm --entrypoint python watermark-remover \
  process_manifest.py \
  --manifest /data/work/watermark-map.json \
  --input /data/input \
  --output /data/output \
  --workdir /data/work \
  --device cuda \
  --overwrite
```

Use `--limit 3` for a small test run.

## Publish to GHCR

Push this repository to GitHub. The workflow at `.github/workflows/docker-ghcr.yml` publishes:

```text
ghcr.io/m19921414377/watermark-remove:latest
ghcr.io/m19921414377/watermark-remove:<branch>
ghcr.io/m19921414377/watermark-remove:sha-<commit>
```

For a private repository, make sure the package visibility and server access are configured in GitHub.

## Deploy on a GPU Server

Install NVIDIA Container Toolkit on the server, then run:

```bash
docker run --rm --gpus all \
  -p 7860:7860 \
  -v /path/to/input:/data/input \
  -v /path/to/output:/data/output \
  -v /path/to/work:/data/work \
  -v watermark-cache:/cache \
  ghcr.io/m19921414377/watermark-remove:latest
```

Batch processing:

```bash
docker run --rm --gpus all \
  -v /path/to/input:/data/input \
  -v /path/to/output:/data/output \
  -v /path/to/work:/data/work \
  -v watermark-cache:/cache \
  --entrypoint python \
  ghcr.io/m19921414377/watermark-remove:latest \
  process_manifest.py \
  --manifest /data/work/watermark-map.json \
  --input /data/input \
  --output /data/output \
  --workdir /data/work \
  --device cuda \
  --overwrite
```

## CPU Build

For a CPU-only image, override the torch index at build time:

```bash
docker build \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu \
  -t watermarkremover:cpu .
```

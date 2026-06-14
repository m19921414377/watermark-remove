# Watermark Remove

Video watermark removal workflow based on LaMa inpainting.

This fork is designed for batches where each video may have a different watermark position. It provides a lightweight WebUI to mark the watermark area for every video, then processes the videos from the saved manifest. Docker and GHCR deployment are supported.

## Features

- Remove fixed-position watermarks from videos with LaMa inpainting.
- Mark a different watermark box for each video.
- Save watermark metadata to `watermark-map.json`.
- Batch process videos from the manifest.
- Preserve the input folder structure in the output folder.
- Supports CUDA GPU processing when available.
- Docker image publishing through GitHub Container Registry.

## Workflow

1. Put source videos in an input folder.
2. Start the WebUI.
3. Draw the watermark region for each video.
4. Save `watermark-map.json`.
5. Run batch processing on a GPU server.
6. Review the cleaned output videos.

## Docker Quick Start

Create local folders:

```bash
mkdir -p data/input data/output data/work
```

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

Draw a rectangle around the watermark for each video. Use a slightly larger box than the visible watermark. The WebUI saves:

```text
data/work/watermark-map.json
```

## Batch Processing

After the manifest is ready, run:

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

For a small test:

```bash
docker compose run --rm --entrypoint python watermark-remover \
  process_manifest.py \
  --manifest /data/work/watermark-map.json \
  --input /data/input \
  --output /data/output \
  --workdir /data/work \
  --device cuda \
  --limit 3 \
  --overwrite
```

## GHCR Deployment

The GitHub Actions workflow publishes Docker images to:

```text
ghcr.io/m19921414377/watermark-remove:latest
```

Run the WebUI on a GPU server:

```bash
docker run --rm --gpus all \
  -p 7860:7860 \
  -v /path/to/input:/data/input \
  -v /path/to/output:/data/output \
  -v /path/to/work:/data/work \
  -v watermark-cache:/cache \
  ghcr.io/m19921414377/watermark-remove:latest
```

Run batch processing:

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

If the repository or package is private, run `docker login ghcr.io` on the server before pulling the image.

## Local Python Usage

Python 3.10 is recommended.

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the per-video watermark WebUI:

```bash
python watermark_manifest_webui.py \
  --input /path/to/videos \
  --workdir /path/to/work \
  --host 0.0.0.0 \
  --port 7860
```

Process videos from the manifest:

```bash
python process_manifest.py \
  --manifest /path/to/work/watermark-map.json \
  --input /path/to/videos \
  --output /path/to/output \
  --workdir /path/to/work \
  --device cuda \
  --overwrite
```

## Manifest Fields

`watermark-map.json` stores one record per video:

- `relative_path`: source video path relative to the input root.
- `watermark`: `yes`, `no`, or `unknown`.
- `mask_mode`: `threshold` or `rect`.
- `x`, `y`, `w`, `h`: watermark box in original video pixels.
- `notes`: optional review notes.

`threshold` builds a mask from bright/dark pixels inside the box. `rect` uses the full rectangle.

## Notes

- This tool is intended for videos you own or are authorized to edit.
- Moving watermarks are not supported yet.
- LaMa is slower than simple blur or delogo filters, but usually produces more natural results.
- For best quality, process only the final clips you plan to use instead of full raw libraries.
- Complex backgrounds may require a larger or adjusted mask and a second processing pass.

## License

This project inherits the upstream license. See [LICENSE](LICENSE).

import argparse
import json
import shutil
from pathlib import Path, PureWindowsPath

import cv2
import numpy as np
from moviepy import VideoFileClip

from watermark_remover import (
    check_gpu,
    get_video_info,
    initialize_lama,
    is_valid_video_file,
    process_video,
)


def relative_path(value: str) -> Path:
    if "\\" in value:
        return Path(*PureWindowsPath(value).parts)
    return Path(value)


def int_or_none(value):
    if value is None or value == "":
        return None
    return int(float(value))


def load_review_frame(workdir: Path, item: dict, video_clip: VideoFileClip) -> np.ndarray:
    frame_value = item.get("frame")
    if frame_value:
        frame_path = workdir / frame_value
        if frame_path.exists():
            frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
            if frame is not None:
                return frame

    timestamp = min(max(video_clip.duration * 0.10, 1.0), 5.0) if video_clip.duration else 0
    frame_rgb = video_clip.get_frame(timestamp)
    return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)


def box_from_item(item: dict) -> tuple[int, int, int, int] | None:
    x = int_or_none(item.get("x"))
    y = int_or_none(item.get("y"))
    w = int_or_none(item.get("w"))
    h = int_or_none(item.get("h"))
    if x is None or y is None or w is None or h is None or w <= 0 or h <= 0:
        return None
    return x, y, w, h


def clamp_box(x: int, y: int, w: int, h: int, width: int, height: int) -> tuple[int, int, int, int]:
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return x, y, w, h


def make_mask(
    item: dict,
    video_clip: VideoFileClip,
    workdir: Path,
    dilate: int,
) -> np.ndarray | None:
    box = box_from_item(item)
    if box is None:
        return None

    width = int(video_clip.w)
    height = int(video_clip.h)
    x, y, w, h = clamp_box(*box, width=width, height=height)
    mask = np.zeros((height, width), dtype=np.uint8)

    mode = item.get("mask_mode", "threshold")
    if mode == "rect":
        mask[y : y + h, x : x + w] = 255
    else:
        frame = load_review_frame(workdir, item, video_clip)
        if frame.shape[1] != width or frame.shape[0] != height:
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        roi = frame[y : y + h, x : x + w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, roi_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask[y : y + h, x : x + w] = roi_mask

    if dilate > 0:
        kernel = np.ones((dilate, dilate), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)

    return mask


def should_process(item: dict, include_unknown: bool) -> bool:
    watermark = item.get("watermark", "unknown")
    if watermark == "yes":
        return True
    if watermark == "unknown" and include_unknown and box_from_item(item) is not None:
        return True
    return False


def process_manifest(args) -> None:
    manifest_path = Path(args.manifest).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    input_root = Path(args.input).resolve() if args.input else Path(manifest["input_root"]).resolve()
    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if args.device:
        device = args.device
    else:
        has_gpu, detected_device, gpu_name = check_gpu()
        device = detected_device
        if has_gpu:
            print(f"GPU detected: {gpu_name}")
        else:
            print("No GPU detected, using CPU for processing")

    print(f"Using device: {device}")
    lama_model, lama_config = initialize_lama(device=device)

    items = manifest.get("items", [])
    processed = 0
    skipped = 0
    for item in items:
        if args.limit and processed >= args.limit:
            break

        rel = relative_path(item["relative_path"])
        src = input_root / rel
        dst = output_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        if not src.exists():
            print(f"Missing source, skipping: {src}")
            skipped += 1
            continue

        if dst.exists() and not args.overwrite:
            print(f"Exists, skipping: {dst}")
            skipped += 1
            continue

        if not should_process(item, args.include_unknown):
            if args.copy_unmarked:
                shutil.copy2(src, dst)
                print(f"Copied unmarked: {rel}")
            else:
                print(f"Unmarked/unknown, skipping: {rel}")
            skipped += 1
            continue

        if not is_valid_video_file(str(src)):
            print(f"Invalid video, skipping: {src}")
            skipped += 1
            continue

        with VideoFileClip(str(src)) as video_clip:
            mask = make_mask(item, video_clip, workdir, args.dilate)
            if mask is None or not np.any(mask):
                print(f"No usable mask, skipping: {rel}")
                skipped += 1
                continue

            output_without_ext = str(dst.with_suffix(""))
            print(f"Processing: {rel}")
            info = process_video(video_clip, output_without_ext, mask, lama_model, lama_config)
            print(f"  Resolution: {info['video_info']['resolution']}")
            print(f"  Duration: {info['video_info']['duration']}")
            print(f"  FPS: {info['video_info']['fps']}")
            print(f"  Processing time: {info['processing_time']}")
            processed += 1

    print(f"Done. Processed: {processed}. Skipped: {skipped}. Output: {output_root}")


def parse_args():
    parser = argparse.ArgumentParser(description="Process videos from per-video watermark manifest")
    parser.add_argument("--manifest", required=True, help="Path to watermark-map.json")
    parser.add_argument("--input", help="Override input root from manifest")
    parser.add_argument("--output", required=True, help="Output root")
    parser.add_argument("--workdir", help="Review workdir containing extracted frames")
    parser.add_argument("--device", choices=["cuda", "cpu"], help="Force processing device")
    parser.add_argument("--dilate", type=int, default=5, help="Mask dilation kernel size")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output files")
    parser.add_argument("--include-unknown", action="store_true", help="Process unknown items if they have a box")
    parser.add_argument("--copy-unmarked", action="store_true", help="Copy unmarked files to output")
    parser.add_argument("--limit", type=int, default=0, help="Process only N marked videos")
    return parser.parse_args()


if __name__ == "__main__":
    process_manifest(parse_args())

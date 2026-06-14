import argparse
import csv
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".flv"}


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Watermark Manifest WebUI</title>
  <style>
    :root { color-scheme: dark; font-family: Arial, sans-serif; }
    body { margin: 0; background: #101214; color: #f0f3f5; }
    header { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #191d21; border-bottom: 1px solid #2c3238; position: sticky; top: 0; z-index: 5; }
    button, select, input { background: #252b31; color: #f0f3f5; border: 1px solid #3b444d; border-radius: 4px; padding: 8px 10px; }
    button:hover { background: #303842; }
    main { display: grid; grid-template-columns: 1fr 340px; gap: 16px; padding: 16px; }
    #stageWrap { overflow: auto; background: #171a1e; border: 1px solid #2c3238; border-radius: 6px; padding: 12px; }
    #stage { max-width: 100%; cursor: crosshair; background: #08090a; display: block; margin: 0 auto; }
    aside { background: #171a1e; border: 1px solid #2c3238; border-radius: 6px; padding: 14px; height: fit-content; }
    .row { margin-bottom: 12px; }
    .label { color: #aab4be; font-size: 12px; margin-bottom: 5px; }
    .value { word-break: break-all; line-height: 1.35; }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; }
    input[type="number"] { width: 74px; }
    textarea { width: 100%; min-height: 72px; resize: vertical; background: #252b31; color: #f0f3f5; border: 1px solid #3b444d; border-radius: 4px; padding: 8px; box-sizing: border-box; }
    .ok { color: #82e09a; }
    .warn { color: #ffd36a; }
    a { color: #8ab4ff; }
  </style>
</head>
<body>
  <header>
    <button id="prevBtn">Prev</button>
    <button id="nextBtn">Next</button>
    <button id="saveBtn">Save</button>
    <button id="clearBtn">No watermark</button>
    <button id="resetBtn">Reset box</button>
    <span id="status"></span>
    <a href="/export.csv" target="_blank">Export CSV</a>
  </header>
  <main>
    <div id="stageWrap">
      <canvas id="stage"></canvas>
    </div>
    <aside>
      <div class="row">
        <div class="label">Item</div>
        <div class="value" id="itemInfo"></div>
      </div>
      <div class="row">
        <div class="label">Path</div>
        <div class="value" id="pathInfo"></div>
      </div>
      <div class="row">
        <div class="label">Resolution</div>
        <div class="value" id="resolutionInfo"></div>
      </div>
      <div class="row">
        <div class="label">Watermark</div>
        <select id="watermarkSelect">
          <option value="unknown">Unknown</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      </div>
      <div class="row">
        <div class="label">Mask mode</div>
        <select id="maskMode">
          <option value="threshold">Threshold inside box</option>
          <option value="rect">Full rectangle</option>
        </select>
      </div>
      <div class="row">
        <div class="label">Original-pixel box: x y w h</div>
        <div class="controls">
          <input id="xInput" type="number">
          <input id="yInput" type="number">
          <input id="wInput" type="number">
          <input id="hInput" type="number">
        </div>
      </div>
      <div class="row">
        <div class="label">Notes</div>
        <textarea id="notes"></textarea>
      </div>
      <div class="row">
        <div class="label">How to use</div>
        <div class="value">Drag a rectangle around the watermark. Use a slightly larger box than the visible mark. Press Save, then Next.</div>
      </div>
    </aside>
  </main>
  <script>
    let items = [];
    let currentIndex = 0;
    let image = new Image();
    let canvas = document.getElementById("stage");
    let ctx = canvas.getContext("2d");
    let dragStart = null;
    let box = null;

    const statusEl = document.getElementById("status");
    const itemInfo = document.getElementById("itemInfo");
    const pathInfo = document.getElementById("pathInfo");
    const resolutionInfo = document.getElementById("resolutionInfo");
    const watermarkSelect = document.getElementById("watermarkSelect");
    const maskMode = document.getElementById("maskMode");
    const xInput = document.getElementById("xInput");
    const yInput = document.getElementById("yInput");
    const wInput = document.getElementById("wInput");
    const hInput = document.getElementById("hInput");
    const notes = document.getElementById("notes");

    function setStatus(text, kind = "") {
      statusEl.textContent = text;
      statusEl.className = kind;
    }

    function currentItem() {
      return items[currentIndex];
    }

    function canvasScale() {
      return image.naturalWidth / canvas.width;
    }

    function originalToCanvasRect(original) {
      if (!original) return null;
      const scale = canvas.width / image.naturalWidth;
      return {
        x: original.x * scale,
        y: original.y * scale,
        w: original.w * scale,
        h: original.h * scale,
      };
    }

    function canvasToOriginalRect(rect) {
      const scale = canvasScale();
      return {
        x: Math.max(0, Math.round(rect.x * scale)),
        y: Math.max(0, Math.round(rect.y * scale)),
        w: Math.max(1, Math.round(rect.w * scale)),
        h: Math.max(1, Math.round(rect.h * scale)),
      };
    }

    function updateInputsFromBox() {
      if (!box) {
        xInput.value = "";
        yInput.value = "";
        wInput.value = "";
        hInput.value = "";
        return;
      }
      const original = canvasToOriginalRect(box);
      xInput.value = original.x;
      yInput.value = original.y;
      wInput.value = original.w;
      hInput.value = original.h;
    }

    function updateBoxFromInputs() {
      const x = parseInt(xInput.value, 10);
      const y = parseInt(yInput.value, 10);
      const w = parseInt(wInput.value, 10);
      const h = parseInt(hInput.value, 10);
      if ([x, y, w, h].some(Number.isNaN) || w <= 0 || h <= 0) {
        box = null;
      } else {
        box = originalToCanvasRect({x, y, w, h});
      }
      draw();
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      if (box) {
        ctx.save();
        ctx.strokeStyle = "#ff3b30";
        ctx.lineWidth = 3;
        ctx.fillStyle = "rgba(255, 59, 48, 0.16)";
        ctx.fillRect(box.x, box.y, box.w, box.h);
        ctx.strokeRect(box.x, box.y, box.w, box.h);
        ctx.restore();
      }
    }

    function loadItem(index) {
      currentIndex = Math.max(0, Math.min(index, items.length - 1));
      const item = currentItem();
      itemInfo.textContent = `#${item.id} / ${items.length}`;
      pathInfo.textContent = item.relative_path;
      resolutionInfo.textContent = `${item.width}x${item.height}`;
      watermarkSelect.value = item.watermark || "unknown";
      maskMode.value = item.mask_mode || "threshold";
      notes.value = item.notes || "";
      xInput.value = item.x ?? "";
      yInput.value = item.y ?? "";
      wInput.value = item.w ?? "";
      hInput.value = item.h ?? "";
      image = new Image();
      image.onload = () => {
        const maxWidth = Math.min(1280, document.getElementById("stageWrap").clientWidth - 28);
        const scale = Math.min(1, maxWidth / image.naturalWidth);
        canvas.width = Math.round(image.naturalWidth * scale);
        canvas.height = Math.round(image.naturalHeight * scale);
        const hasBox = item.x !== null && item.y !== null && item.w !== null && item.h !== null && item.w !== "" && item.h !== "";
        box = hasBox ? originalToCanvasRect({x: Number(item.x), y: Number(item.y), w: Number(item.w), h: Number(item.h)}) : null;
        draw();
      };
      image.src = `/frame/${item.id}?t=${Date.now()}`;
      setStatus(item.watermark === "yes" ? "Marked" : item.watermark === "no" ? "No watermark" : "Unsaved", item.watermark === "unknown" ? "warn" : "ok");
    }

    async function saveItem(markNo = false) {
      const item = currentItem();
      let original = box ? canvasToOriginalRect(box) : null;
      if (markNo) {
        original = null;
        watermarkSelect.value = "no";
      }
      const payload = {
        watermark: watermarkSelect.value,
        mask_mode: maskMode.value,
        x: original ? original.x : "",
        y: original ? original.y : "",
        w: original ? original.w : "",
        h: original ? original.h : "",
        notes: notes.value || "",
      };
      if (payload.watermark !== "no" && original) payload.watermark = "yes";
      const res = await fetch(`/api/item/${item.id}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        setStatus("Save failed", "warn");
        return;
      }
      Object.assign(item, payload);
      setStatus("Saved", "ok");
    }

    canvas.addEventListener("mousedown", (e) => {
      const r = canvas.getBoundingClientRect();
      dragStart = {x: e.clientX - r.left, y: e.clientY - r.top};
      box = {x: dragStart.x, y: dragStart.y, w: 0, h: 0};
      draw();
    });

    canvas.addEventListener("mousemove", (e) => {
      if (!dragStart) return;
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      box = {
        x: Math.min(dragStart.x, x),
        y: Math.min(dragStart.y, y),
        w: Math.abs(x - dragStart.x),
        h: Math.abs(y - dragStart.y),
      };
      draw();
      updateInputsFromBox();
    });

    window.addEventListener("mouseup", () => {
      if (!dragStart) return;
      dragStart = null;
      updateInputsFromBox();
      watermarkSelect.value = "yes";
    });

    [xInput, yInput, wInput, hInput].forEach(el => el.addEventListener("change", updateBoxFromInputs));
    document.getElementById("prevBtn").onclick = () => loadItem(currentIndex - 1);
    document.getElementById("nextBtn").onclick = async () => { await saveItem(false); loadItem(currentIndex + 1); };
    document.getElementById("saveBtn").onclick = () => saveItem(false);
    document.getElementById("clearBtn").onclick = async () => { box = null; updateInputsFromBox(); await saveItem(true); draw(); };
    document.getElementById("resetBtn").onclick = () => { box = null; updateInputsFromBox(); watermarkSelect.value = "unknown"; draw(); };
    window.addEventListener("keydown", async (e) => {
      if (e.key === "ArrowRight") { await saveItem(false); loadItem(currentIndex + 1); }
      if (e.key === "ArrowLeft") loadItem(currentIndex - 1);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveItem(false); }
    });

    fetch("/api/items").then(r => r.json()).then(data => {
      items = data.items;
      loadItem(0);
    });
  </script>
</body>
</html>
"""


def run(cmd):
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def ffprobe_duration(ffprobe: Path, src: Path) -> float:
    result = run([
        str(ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(src),
    ])
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def ffprobe_size(ffprobe: Path, src: Path) -> tuple[int, int]:
    result = run([
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(src),
    ])
    width, height = result.stdout.strip().split("x")
    return int(width), int(height)


def extract_frame(ffmpeg: Path, src: Path, dst: Path, duration: float, refresh: bool) -> None:
    if dst.exists() and not refresh:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    timestamp = min(max(duration * 0.10, 1.0), 5.0) if duration > 0 else 1.0
    run([
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{timestamp:.2f}",
        "-i",
        str(src),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(dst),
    ])


def scan_or_load_manifest(input_root: Path, workdir: Path, ffmpeg: Path, ffprobe: Path, refresh: bool) -> dict:
    manifest_path = workdir / "watermark-map.json"
    if manifest_path.exists() and not refresh:
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    previous_by_path = {}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_by_path = {item["relative_path"]: item for item in previous.get("items", [])}

    files = [p for p in sorted(input_root.rglob("*")) if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    frames_dir = workdir / "frames"
    items = []
    for idx, src in enumerate(files, start=1):
        rel = str(src.relative_to(input_root))
        duration = ffprobe_duration(ffprobe, src)
        width, height = ffprobe_size(ffprobe, src)
        frame_name = f"{idx:04d}.jpg"
        frame_path = frames_dir / frame_name
        extract_frame(ffmpeg, src, frame_path, duration, refresh=refresh)
        old = previous_by_path.get(rel, {})
        items.append({
            "id": idx,
            "relative_path": rel,
            "width": width,
            "height": height,
            "duration_seconds": duration,
            "frame": str(Path("frames") / frame_name),
            "watermark": old.get("watermark", "unknown"),
            "mask_mode": old.get("mask_mode", "threshold"),
            "x": old.get("x", ""),
            "y": old.get("y", ""),
            "w": old.get("w", ""),
            "h": old.get("h", ""),
            "notes": old.get("notes", ""),
        })
        print(f"{idx:04d}/{len(files)} {rel}")

    manifest = {"input_root": str(input_root), "items": items}
    workdir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_manifest(workdir: Path, manifest: dict) -> None:
    (workdir / "watermark-map.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    manifest = None
    workdir = None

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, content_type="text/html; charset=utf-8", status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_text(INDEX_HTML)
            return
        if parsed.path == "/api/items":
            self.send_json({"items": self.manifest["items"]})
            return
        if parsed.path.startswith("/frame/"):
            item_id = int(parsed.path.rsplit("/", 1)[-1])
            item = next((i for i in self.manifest["items"] if i["id"] == item_id), None)
            if not item:
                self.send_error(404)
                return
            frame_path = self.workdir / item["frame"]
            if not frame_path.exists():
                self.send_error(404)
                return
            body = frame_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/export.csv":
            fieldnames = ["id", "relative_path", "width", "height", "duration_seconds", "watermark", "mask_mode", "x", "y", "w", "h", "notes"]
            rows = []
            for item in self.manifest["items"]:
                rows.append({key: item.get(key, "") for key in fieldnames})
            from io import StringIO
            buffer = StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            self.send_text(buffer.getvalue(), content_type="text/csv; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/item/"):
            self.send_error(404)
            return
        item_id = int(parsed.path.rsplit("/", 1)[-1])
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        item = next((i for i in self.manifest["items"] if i["id"] == item_id), None)
        if not item:
            self.send_error(404)
            return
        for key in ["watermark", "mask_mode", "x", "y", "w", "h", "notes"]:
            if key in payload:
                item[key] = payload[key]
        write_manifest(self.workdir, self.manifest)
        self.send_json({"ok": True, "item": item})


def main():
    parser = argparse.ArgumentParser(description="Per-video watermark mask WebUI")
    parser.add_argument("--input", "-i", required=True, help="Input video root")
    parser.add_argument("--workdir", "-w", default=".watermark-review", help="Review work directory")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Path to ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe", help="Path to ffprobe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--refresh", action="store_true", help="Rescan videos and re-extract frames")
    args = parser.parse_args()

    input_root = Path(args.input).resolve()
    workdir = Path(args.workdir).resolve()
    manifest = scan_or_load_manifest(
        input_root=input_root,
        workdir=workdir,
        ffmpeg=Path(args.ffmpeg),
        ffprobe=Path(args.ffprobe),
        refresh=args.refresh,
    )

    Handler.manifest = manifest
    Handler.workdir = workdir
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Open http://{args.host}:{args.port}")
    print(f"Manifest: {workdir / 'watermark-map.json'}")
    server.serve_forever()


if __name__ == "__main__":
    main()

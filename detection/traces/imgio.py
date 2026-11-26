"""Image / YOLO-label I/O that survives Korean (non-ASCII) Windows paths."""

from pathlib import Path

import cv2
import numpy as np

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def imread(path):
    data = np.fromfile(str(path), np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise IOError(f"cannot read image: {path}")
    return img


def imwrite(path, img, quality=95):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise IOError(f"cannot encode image: {path}")
    buf.tofile(str(path))


def list_images(folder):
    folder = Path(folder)
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXTS)


def label_path_for(img_path):
    """images/.../x.jpg -> labels/.../x.txt (ultralytics convention)."""
    p = Path(img_path)
    parts = list(p.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "images":
            parts[i] = "labels"
            return Path(*parts).with_suffix(".txt")
    return p.with_suffix(".txt")


def read_yolo(label_path, w, h):
    """Return (N,5) array [cls, x1, y1, x2, y2] in pixels. Missing file = no objects."""
    p = Path(label_path)
    if not p.exists():
        return np.zeros((0, 5), np.float32)
    rows = [r.split() for r in p.read_text(encoding="utf-8").splitlines() if r.strip()]
    if not rows:
        return np.zeros((0, 5), np.float32)
    a = np.array([[float(v) for v in r[:5]] for r in rows], np.float32)
    cls, cx, cy, bw, bh = a.T
    return np.stack([cls, (cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h], 1)


def write_yolo(label_path, boxes, w, h):
    """boxes: (N,5) [cls, x1, y1, x2, y2] in pixels. Writes an empty file for negatives."""
    p = Path(label_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for c, x1, y1, x2, y2 in np.asarray(boxes).reshape(-1, 5):
        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        bw, bh = (x2 - x1) / w, (y2 - y1) / h
        lines.append(f"{int(c)} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

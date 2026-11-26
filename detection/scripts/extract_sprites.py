"""Cut dark objects (droppings) out of photos taken on a plain light background
(white paper, coloured card) into RGBA sprites for synthetic compositing.

  python scripts/extract_sprites.py --images a.jpg b.jpg --out data/sprites/rodent_dropping --prefix wiki

Objects are found as connected regions clearly darker than the (median) background;
coins, ruler marks and shadows are rejected by size, fill ratio and darkness.
A contact sheet <out>/_sheet_<prefix>.jpg is written for visual review - delete bad sprites by hand.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces.imgio import imread  # noqa: E402


def extract(img, min_area_frac=2e-5, max_area_frac=0.02, dark_margin=60, pad=4, alpha_offset=15):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    bg = cv2.medianBlur(g.astype(np.uint8), 51).astype(np.float32)  # local background level
    dark = (bg - g) > dark_margin
    dark = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    H, W = g.shape
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (min_area_frac * H * W <= area <= max_area_frac * H * W):
            continue
        if area / (w * h) < 0.35 or max(w, h) / max(1, min(w, h)) > 5:  # thin lines (ruler), sparse junk
            continue
        if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:
            continue
        x1, y1, x2, y2 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
        patch = img[y1:y2, x1:x2]
        # soft alpha: darkness relative to local background, limited to the component (+1px)
        m = cv2.dilate((lab[y1:y2, x1:x2] == i).astype(np.uint8), np.ones((3, 3), np.uint8))
        a = np.clip((bg[y1:y2, x1:x2] - g[y1:y2, x1:x2] - alpha_offset) / 50, 0, 1) * m
        a = cv2.GaussianBlur(a, (0, 0), 0.7)
        out.append(np.dstack([patch, (a * 255).astype(np.uint8)]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", default="ext")
    ap.add_argument("--dark-margin", type=float, default=60)
    ap.add_argument("--alpha-offset", type=float, default=15, help="raise on coloured backgrounds to drop the colour fringe")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sheet = []
    for p in args.images:
        img = imread(p)
        sprites = extract(img, dark_margin=args.dark_margin, alpha_offset=args.alpha_offset)
        for k, s in enumerate(sprites):
            name = f"{args.prefix}_{Path(p).stem}_{k:03d}.png"
            cv2.imencode(".png", s)[1].tofile(str(out / name))
            vis = s[..., :3].astype(np.float32) * (s[..., 3:] / 255) + 255 * (1 - s[..., 3:] / 255)
            t = cv2.resize(vis.astype(np.uint8), (96, 96), interpolation=cv2.INTER_AREA)
            cv2.putText(t, f"{Path(p).stem[-2:]}_{k}", (2, 12), 0, 0.35, (0, 0, 255), 1)
            sheet.append(t)
        print(f"{p}: {len(sprites)} sprites")
    if sheet:
        sheet += [np.full((96, 96, 3), 255, np.uint8)] * (-len(sheet) % 10)
        rows = [np.hstack(sheet[i:i + 10]) for i in range(0, len(sheet), 10)]
        cv2.imencode(".jpg", np.vstack(rows))[1].tofile(str(out / f"_sheet_{args.prefix}.jpg"))


if __name__ == "__main__":
    main()

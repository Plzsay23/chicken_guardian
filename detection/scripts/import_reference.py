"""Turn references/images/라벨링예시_배설물_boxes.json (the only real labelled photo so far)
into a raw YOLO dataset used as a sim-to-real sanity check.

boxes.json rows are [x, y, w, h, darkness] in original-image pixels (class rodent_dropping).
The photo is NOT used for training by default - it is the held-out real test.
Pass --sprites to cut its droppings out as RGBA sprites instead (then don't evaluate on it).
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces import ROOT  # noqa: E402
from traces.imgio import imread, write_yolo  # noqa: E402
from traces.synth import cut_sprite  # noqa: E402

REF = ROOT.parent / "references" / "images"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=str(REF / "house_mouse_droppings_NYSIPM_CCBY2.jpg"))
    ap.add_argument("--boxes", default=str(REF / "라벨링예시_배설물_boxes.json"))
    ap.add_argument("--out", default=str(ROOT / "data" / "raw" / "reference"))
    ap.add_argument("--sprites", action="store_true", help="export cut-outs to data/sprites/rodent_dropping/")
    args = ap.parse_args()

    img = imread(args.image)
    h, w = img.shape[:2]
    rows = json.load(open(args.boxes, encoding="utf-8"))
    boxes = np.array([[0, x, y, x + bw, y + bh] for x, y, bw, bh, _ in rows], np.float32)

    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    name = Path(args.image).stem
    shutil.copyfile(args.image, out / "images" / f"{name}.jpg")
    write_yolo(out / "labels" / f"{name}.txt", boxes, w, h)
    print(f"{len(boxes)} boxes -> {out}")

    if args.sprites:
        import cv2

        sd = ROOT / "data" / "sprites" / "rodent_dropping"
        sd.mkdir(parents=True, exist_ok=True)
        for i, (x, y, bw, bh, _) in enumerate(rows):
            rgba = cut_sprite(img, int(x), int(y), int(bw), int(bh))
            cv2.imencode(".png", rgba)[1].tofile(str(sd / f"ref_{i:03d}.png"))
        print(f"{len(rows)} sprites -> {sd}  (now evaluating on this photo is leaky)")


if __name__ == "__main__":
    main()

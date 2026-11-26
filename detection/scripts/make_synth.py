"""Generate full-resolution synthetic frames as a raw YOLO dataset.

Output: <out>/images/*.jpg, <out>/labels/*.txt, <out>/meta.jsonl
Then tile it with prepare_dataset.py exactly like real photos.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces import ROOT, load_cfg  # noqa: E402
from traces.imgio import imwrite, write_yolo  # noqa: E402
from traces.synth import SynthGenerator  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=None)
    ap.add_argument("--out", default=str(ROOT / "data" / "raw" / "synth"))
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bg-dir", default=str(ROOT / "data" / "backgrounds"), help="farm ground photos without traces")
    ap.add_argument("--sprite-dir", default=str(ROOT / "data" / "sprites"), help="<class>/*.png RGBA cut-outs")
    ap.add_argument("--preview", type=int, default=6, help="also save this many frames with boxes drawn")
    args = ap.parse_args()

    cfg = load_cfg(args.cfg)
    gen = SynthGenerator(cfg, args.bg_dir, args.sprite_dir, args.seed)
    out = Path(args.out)
    print(f"backgrounds: {len(gen.bg_paths)} photos (+procedural) | sprite bank: { {k: len(v) for k, v in gen.bank.items()} }")
    n_obj = [0] * len(cfg["classes"])
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "meta.jsonl", "w", encoding="utf-8") as meta:
        for i in range(args.n):
            img, boxes, info = gen.frame()
            name = f"synth_s{args.seed}_{i:05d}"
            imwrite(out / "images" / f"{name}.jpg", img, 92)
            write_yolo(out / "labels" / f"{name}.txt", boxes, img.shape[1], img.shape[0])
            meta.write(json.dumps({"name": name, "n": len(boxes), **info}) + "\n")
            for c in boxes[:, 0]:
                n_obj[int(c)] += 1
            if i < args.preview:
                vis = img.copy()
                for c, x1, y1, x2, y2 in boxes:
                    col = (0, 255, 0) if c == 0 else (0, 200, 255)
                    cv2.rectangle(vis, (int(x1) - 2, int(y1) - 2), (int(x2) + 2, int(y2) + 2), col, 1)
                imwrite(out / "preview" / f"{name}.jpg", vis, 90)
            if (i + 1) % 100 == 0:
                print(f"{i + 1}/{args.n}")
    print("objects per class:", dict(zip(cfg["classes"], n_obj)))


if __name__ == "__main__":
    main()

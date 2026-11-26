"""Run the sliced detector on images / a folder / a video and save JSON + annotated output.

  python scripts/infer.py --weights best.pt --source some/folder --mode confirm
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces import ROOT, load_cfg  # noqa: E402
from traces.imgio import IMG_EXTS, imread, imwrite, list_images  # noqa: E402
from traces.sliced import SlicedDetector, draw  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=None)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--source", required=True, help="image, folder or video file")
    ap.add_argument("--mode", default="confirm", choices=["patrol", "confirm"])
    ap.add_argument("--conf", type=float, default=None, help="override mode conf")
    ap.add_argument("--device", default=None)
    ap.add_argument("--vid-stride", type=int, default=5, help="process every n-th video frame")
    ap.add_argument("--out", default=str(ROOT / "runs" / "infer"))
    args = ap.parse_args()

    cfg = load_cfg(args.cfg)
    names = cfg["classes"]
    m = dict(cfg["infer"][args.mode])
    if args.conf is not None:
        m["conf"] = args.conf
    det = SlicedDetector(args.weights, cfg["tile"]["size"], device=args.device, names=names)
    out = Path(args.out)
    src = Path(args.source)

    def frames():
        if src.is_dir():
            for p in list_images(src):
                yield p.stem, imread(p)
        elif src.suffix.lower() in IMG_EXTS:
            yield src.stem, imread(src)
        else:
            cap = cv2.VideoCapture(str(src))
            i = 0
            while True:
                ok, f = cap.read()
                if not ok:
                    break
                if i % args.vid_stride == 0:
                    yield f"{src.stem}_{i:06d}", f
                i += 1

    results = []
    for name, img in frames():
        t = time.perf_counter()
        d = det(img, conf=m["conf"], overlap=m["overlap"], scale=m["scale"], tta=m["tta"], iou_merge=cfg["infer"]["iou_merge"])
        dt = (time.perf_counter() - t) * 1000
        results.append({"image": name, "ms": round(dt, 1), "detections": d.to_list(names)})
        imwrite(out / f"{name}.jpg", draw(img, d, names), 90)
        counts = {n: int((d.classes == i).sum()) for i, n in enumerate(names)}
        print(f"{name}: {counts} {dt:.0f} ms")
    out.mkdir(parents=True, exist_ok=True)
    (out / "detections.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    main()

"""Full-frame evaluation of the sliced detector (the number that matters on the robot).

  python scripts/evaluate.py --weights runs/x/weights/best.pt --images data/tiles/x/val_full.txt
  python scripts/evaluate.py --weights best.pt --images data/raw/reference/images

Writes <out>/metrics.json and annotated frames (green = TP, red = FP, blue = missed GT).
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces import ROOT, load_cfg  # noqa: E402
from traces.imgio import imread, imwrite, label_path_for, list_images, read_yolo  # noqa: E402
from traces.metrics import best_conf, drop_ignored, evaluate, match_image  # noqa: E402
from traces.sliced import SlicedDetector  # noqa: E402


def gather(images_arg):
    p = Path(images_arg)
    if p.suffix == ".txt":
        return [Path(l.strip()) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return list_images(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=None)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--images", required=True, help="folder of full-res images, or val_full.txt")
    ap.add_argument("--mode", default="confirm", choices=["patrol", "confirm"])
    ap.add_argument("--iou", type=float, default=0.3, help="match IoU (loose on purpose for tiny boxes)")
    ap.add_argument("--conf", type=float, default=None, help="operating point; default = mode conf from cfg")
    ap.add_argument("--tune-conf", action="store_true", help="also report the F1-optimal conf for class 0")
    ap.add_argument("--device", default=None)
    ap.add_argument("--max-vis", type=int, default=20)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = load_cfg(args.cfg)
    names = cfg["classes"]
    m = cfg["infer"][args.mode]
    conf_op = args.conf if args.conf is not None else m["conf"]
    det = SlicedDetector(args.weights, cfg["tile"]["size"], device=args.device, names=names)
    out = Path(args.out or Path(args.weights).resolve().parents[1] / f"eval_{args.mode}_{Path(args.images).stem}")
    out.mkdir(parents=True, exist_ok=True)

    records = []
    paths = gather(args.images)
    for i, p in enumerate(paths):
        img = imread(p)
        h, w = img.shape[:2]
        gt = read_yolo(label_path_for(p), w, h)
        d = det(img, conf=0.01, overlap=m["overlap"], scale=m["scale"], tta=m["tta"], iou_merge=cfg["infer"]["iou_merge"])
        ign = gt[gt[:, 0] < 0, 1:]  # class -1 rows = ignore regions
        gt = gt[gt[:, 0] >= 0]
        d.boxes, d.scores, d.classes = drop_ignored(d.boxes, d.scores, d.classes, ign)
        records.append({
            "name": p.name, "pred_boxes": d.boxes, "pred_scores": d.scores, "pred_cls": d.classes,
            "gt_boxes": gt[:, 1:], "gt_cls": gt[:, 0].astype(int),
        })
        if i < args.max_vis:
            vis = img.copy()
            for c in range(len(names)):
                pm = (d.classes == c) & (d.scores >= conf_op)
                gm = gt[:, 0] == c
                tp, ps, gt_hit = match_image(d.boxes[pm], d.scores[pm], gt[gm, 1:], args.iou)
                pb = d.boxes[pm][np.argsort(-d.scores[pm])]
                for b, ok, s in zip(pb, tp, ps):
                    col = (0, 220, 0) if ok else (0, 0, 255)
                    cv2.rectangle(vis, (int(b[0]) - 3, int(b[1]) - 3), (int(b[2]) + 3, int(b[3]) + 3), col, 2)
                    cv2.putText(vis, f"{c}:{s:.2f}", (int(b[0]), int(b[1]) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
                for b, hit in zip(gt[gm, 1:], gt_hit):
                    if hit < 0:
                        cv2.rectangle(vis, (int(b[0]) - 5, int(b[1]) - 5), (int(b[2]) + 5, int(b[3]) + 5), (255, 80, 0), 2)
            imwrite(out / "vis" / f"{p.stem}.jpg", vis, 90)

    res = evaluate(records, len(names), args.iou, conf_op)
    res.update({"weights": str(args.weights), "mode": args.mode, "iou_match": args.iou, "conf": conf_op})
    if args.tune_conf:
        t, f1 = best_conf(records, len(names), args.iou)
        res["best_conf_cls0"] = {"conf": t, "F1": f1}
    res["per_class"] = {names[int(k)]: v for k, v in res["per_class"].items()}
    (out / "metrics.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{len(records)} images | mode={args.mode} conf={conf_op} IoU>={args.iou}")
    for n, v in res["per_class"].items():
        print(f"  {n:16s} GT={v['n_gt']:5d} AP={v['AP']:.3f} P={v['precision']:.3f} R={v['recall']:.3f} "
              f"F1={v['F1']:.3f} FPPI={v['FPPI']:.2f} by-size={v['recall_by_size']}")
    print("  image presence (cls0):", res["image_presence_cls0"])
    if "best_conf_cls0" in res:
        print("  best conf cls0:", res["best_conf_cls0"])
    print("->", out)


if __name__ == "__main__":
    main()

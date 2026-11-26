"""Raw full-resolution datasets -> tiled YOLO dataset for training.

Each raw dir looks like  <raw>/images/[session/]*.jpg  +  <raw>/labels/[session/]*.txt
(labels in YOLO format; missing label file = image with no traces = negative).

Split is done per *group* before tiling, so overlapping tiles of one photo never land
in both train and val. Group = first sub-folder under images/ (one capture session /
one farm visit) if present, else the image itself.

Output:
  <out>/images/{train,val}/*.jpg, <out>/labels/{train,val}/*.txt
  <out>/data.yaml                 (for ultralytics)
  <out>/val_full.txt              (full-res val images, for evaluate.py)
"""

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces import ROOT, load_cfg  # noqa: E402
from traces.imgio import imread, imwrite, label_path_for, list_images, read_yolo, write_yolo  # noqa: E402
from traces.tiling import clip_boxes_to_tile, partially_cut, tile_grid  # noqa: E402


def group_of(img_path, raw_dir):
    rel = Path(img_path).relative_to(Path(raw_dir) / "images")
    return f"{Path(raw_dir).name}/{rel.parts[0] if len(rel.parts) > 1 else rel.stem}"


def tile_image(img_path, split, out, tcfg, rng, prefix, stats):
    img = imread(img_path)
    h, w = img.shape[:2]
    boxes = read_yolo(label_path_for(img_path), w, h)
    pos, neg = [], []
    for t in tile_grid(w, h, tcfg["size"], tcfg["overlap"]):
        tb = clip_boxes_to_tile(boxes, t, tcfg["min_visibility"])
        if len(tb):
            pos.append((t, tb))
        elif not partially_cut(boxes, t, tcfg["min_visibility"]):
            neg.append((t, tb))
    # images without any object contribute a few negatives so the ratio stays sane
    n_neg = int(round(len(pos) * tcfg["neg_ratio"])) if pos else min(len(neg), 2)
    if len(neg) > n_neg:
        neg = [neg[i] for i in rng.choice(len(neg), n_neg, replace=False)]
    for k, (t, tb) in enumerate(pos + neg):
        x1, y1, x2, y2 = t
        name = f"{prefix}_{x1}_{y1}"
        imwrite(out / "images" / split / f"{name}.jpg", img[y1:y2, x1:x2], 95)
        write_yolo(out / "labels" / split / f"{name}.txt", tb, x2 - x1, y2 - y1)
        stats[split]["tiles"] += 1
        stats[split]["neg"] += int(len(tb) == 0)
        stats[split]["objs"] += len(tb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=None)
    ap.add_argument("--raw", nargs="+", required=True, help="raw dataset dirs (train/val split by group)")
    ap.add_argument("--val-raw", nargs="*", default=[], help="raw dirs used entirely as validation")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--out", default=str(ROOT / "data" / "tiles" / "default"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg(args.cfg)
    tcfg = cfg["tile"]
    out = Path(args.out)
    if out.exists():
        if not args.overwrite:
            sys.exit(f"{out} exists - pass --overwrite to rebuild it")
        shutil.rmtree(out)
    rng = np.random.default_rng(args.seed)

    jobs = []  # (img_path, split)
    for raw in args.raw:
        imgs = list_images(Path(raw) / "images")
        groups = sorted({group_of(p, raw) for p in imgs})
        rng.shuffle(groups)
        n_val = int(round(len(groups) * args.val_frac)) if args.val_frac > 0 else 0
        if args.val_frac > 0 and len(groups) > 1:
            n_val = max(1, n_val)
        val_groups = set(groups[:n_val])
        jobs += [(p, "val" if group_of(p, raw) in val_groups else "train") for p in imgs]
        print(f"{raw}: {len(imgs)} images, {len(groups)} groups, {n_val} groups -> val")
    for raw in args.val_raw:
        imgs = list_images(Path(raw) / "images")
        jobs += [(p, "val") for p in imgs]
        print(f"{raw}: {len(imgs)} images -> val (held out)")

    stats = {s: {"images": 0, "tiles": 0, "neg": 0, "objs": 0} for s in ("train", "val")}
    val_full = []
    for i, (p, split) in enumerate(jobs):
        prefix = f"{Path(p).stem}_{i:05d}"
        tile_image(p, split, out, tcfg, rng, prefix, stats)
        stats[split]["images"] += 1
        if split == "val":
            val_full.append(str(Path(p).resolve()))
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(jobs)}")

    data = {
        "path": str(out.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {i: n for i, n in enumerate(cfg["classes"])},
    }
    with open(out / "data.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    (out / "val_full.txt").write_text("\n".join(val_full) + "\n", encoding="utf-8")
    for s, v in stats.items():
        print(f"{s}: {v}")
    if stats["val"]["tiles"] == 0:
        print("WARNING: no val tiles - ultralytics needs a non-empty val split")
    print(f"-> {out / 'data.yaml'}")


if __name__ == "__main__":
    main()

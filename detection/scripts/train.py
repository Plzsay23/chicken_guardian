"""Train the tiny-trace detector on a tiled dataset (prepare_dataset.py output).

Stage 1 (bootstrap): synthetic tiles, P2 architecture initialised from COCO yolo11{s}.pt
Stage 2 (fine-tune): real (+ some synthetic) tiles, --model <stage1 best.pt>
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces import ROOT, load_cfg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=None)
    ap.add_argument("--data", required=True, help="data.yaml from prepare_dataset.py")
    ap.add_argument("--model", default=str(ROOT / "models" / "yolo11s-p2.yaml"),
                    help="architecture yaml (scale letter in file name) or a .pt to fine-tune")
    ap.add_argument("--pretrained", default="yolo11s.pt", help="COCO weights transferred into a yaml model; 'none' to skip")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default=None, help="0 | cpu | 0,1 ; default auto")
    ap.add_argument("--optimizer", default="auto", help="auto ignores --lr0; give SGD/AdamW to use it")
    ap.add_argument("--lr0", type=float, default=0.01)
    ap.add_argument("--patience", type=int, default=25)
    ap.add_argument("--cache", default="False", help="False | ram | disk")
    ap.add_argument("--project", default=str(ROOT / "runs"))
    ap.add_argument("--name", default="traces")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    from ultralytics import YOLO

    cfg = load_cfg(args.cfg)
    imgsz = cfg["tile"]["size"]
    model = YOLO(args.model, task="detect")
    if args.model.endswith(".yaml") and args.pretrained.lower() != "none":
        model.load(args.pretrained)  # transfers every layer whose name+shape match (backbone, P3-P5 neck)

    cache = {"false": False, "ram": "ram", "disk": "disk", "true": True}[args.cache.lower()]
    model.train(
        data=args.data,
        imgsz=imgsz,
        epochs=args.epochs,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        optimizer=args.optimizer,
        lr0=args.lr0,
        patience=args.patience,
        cache=cache,
        project=args.project,
        name=args.name,
        seed=args.seed,
        exist_ok=False,
        # augmentation tuned for 5-40 px objects on a fixed-height ground camera:
        scale=0.25,        # default 0.5 shrinks 8-px droppings to 4 px - below what P2 can resolve
        translate=0.1,
        degrees=0.0,       # rotated axis-aligned boxes inflate badly for elongated objects
        fliplr=0.5,
        flipud=0.5,        # ground seen from above: up/down is as valid as left/right
        mosaic=1.0,
        close_mosaic=10,
        mixup=0.0,
        hsv_h=0.015, hsv_s=0.5, hsv_v=0.45,
        erasing=0.0,
        max_det=300,
        plots=True,
    )
    print("best:", Path(model.trainer.save_dir) / "weights" / "best.pt")


if __name__ == "__main__":
    main()

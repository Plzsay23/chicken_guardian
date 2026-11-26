"""Export trained weights for the robot.

On the PC:     ONNX (portable; also a sanity check that the P2 graph exports cleanly)
On the Jetson: TensorRT engine. Must be built ON the Jetson - engines are tied to the GPU
               and TensorRT version they were built with.

  python scripts/export.py --weights best.pt --format onnx
  python scripts/export.py --weights best.pt --format engine --half          # Jetson, FP16
  python scripts/export.py --weights best.pt --format engine --int8 --data data.yaml  # Jetson, INT8 calib
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traces import load_cfg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=None)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--format", default="onnx", choices=["onnx", "engine"])
    ap.add_argument("--half", action="store_true")
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--data", default=None, help="data.yaml for INT8 calibration (uses val tiles)")
    ap.add_argument("--batch", type=int, default=1, help="static batch; sliced inference sends tiles one by one at 1")
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    from ultralytics import YOLO

    imgsz = load_cfg(args.cfg)["tile"]["size"]
    kw = dict(format=args.format, imgsz=imgsz, batch=args.batch, half=args.half, int8=args.int8, device=args.device)
    if args.format == "onnx":
        kw.update(opset=17, simplify=True, dynamic=False)
    if args.int8:
        if not args.data:
            sys.exit("--int8 needs --data for calibration")
        kw["data"] = args.data
    path = YOLO(args.weights).export(**kw)
    print("->", path)


if __name__ == "__main__":
    main()

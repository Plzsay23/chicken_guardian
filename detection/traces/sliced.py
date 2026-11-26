"""Sliced (tiled) inference: full-res frame -> tiles -> YOLO -> merged detections.

Works with any ultralytics-loadable weights: .pt (PC), .onnx, .engine (Jetson TensorRT).
Used by evaluate.py, infer.py and the ROS 2 node, so they all see the same thing.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from .tiling import tile_grid


@dataclass
class Detections:
    boxes: np.ndarray   # (N,4) x1,y1,x2,y2 in original-frame pixels
    scores: np.ndarray  # (N,)
    classes: np.ndarray  # (N,) int

    def __len__(self):
        return len(self.scores)

    def to_list(self, names=None):
        return [
            {
                "cls": int(c),
                "name": names[int(c)] if names else str(int(c)),
                "score": round(float(s), 4),
                "box": [round(float(v), 1) for v in b],
            }
            for b, s, c in zip(self.boxes, self.scores, self.classes)
        ]


def ios_nms(boxes, scores, classes, thr=0.5):
    """Class-wise greedy NMS using intersection-over-smaller.

    IoU under-merges a full box with the clipped copy of it from a neighbouring tile
    (the clipped one is small, so IoU is low); IoS treats "one inside the other" as duplicate.
    """
    keep = []
    for c in np.unique(classes):
        idx = np.where(classes == c)[0]
        idx = idx[np.argsort(-scores[idx])]
        b = boxes[idx]
        area = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
        alive = np.ones(len(idx), bool)
        for i in range(len(idx)):
            if not alive[i]:
                continue
            keep.append(idx[i])
            ix = np.clip(np.minimum(b[i, 2], b[i + 1:, 2]) - np.maximum(b[i, 0], b[i + 1:, 0]), 0, None)
            iy = np.clip(np.minimum(b[i, 3], b[i + 1:, 3]) - np.maximum(b[i, 1], b[i + 1:, 1]), 0, None)
            ios = ix * iy / np.maximum(np.minimum(area[i], area[i + 1:]), 1e-6)
            alive[i + 1:] &= ios < thr
    keep = np.array(keep, int)
    return keep[np.argsort(-scores[keep])] if len(keep) else keep


class SlicedDetector:
    def __init__(self, weights, tile=640, device=None, half=False, batch=8, names=None):
        from ultralytics import YOLO

        self.model = YOLO(weights, task="detect")
        self.tile = tile
        self.device = device
        self.half = half
        # exported engines are usually built with a fixed batch; keep 1 for those
        self.batch = 1 if str(weights).endswith((".engine", ".onnx")) else batch
        self.names = names or self.model.names

    def _run(self, crops, conf):
        out = []
        for i in range(0, len(crops), self.batch):
            res = self.model.predict(
                crops[i:i + self.batch], imgsz=self.tile, conf=conf, iou=0.6,
                device=self.device, half=self.half, verbose=False, max_det=300,
            )
            for r in res:
                b = r.boxes
                out.append((b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy().astype(int)))
        return out

    def __call__(self, frame, conf=0.25, overlap=0.2, scale=1.0, tta=False, iou_merge=0.5):
        """frame: BGR uint8 full-resolution image. Returns Detections in frame pixels."""
        src = frame if scale == 1.0 else cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        h, w = src.shape[:2]
        tiles = tile_grid(w, h, self.tile, overlap)
        crops = [np.ascontiguousarray(src[y1:y2, x1:x2]) for x1, y1, x2, y2 in tiles]
        variants = [(None, crops)]
        if tta:
            variants += [(1, [c[:, ::-1].copy() for c in crops]), (0, [c[::-1].copy() for c in crops])]
        B, S, C = [], [], []
        for flip, cs in variants:
            for (x1, y1, x2, y2), (bb, ss, cc) in zip(tiles, self._run(cs, conf)):
                if len(ss) == 0:
                    continue
                bb = bb.copy()
                tw, th = x2 - x1, y2 - y1
                if flip == 1:
                    bb[:, [0, 2]] = tw - bb[:, [2, 0]]
                elif flip == 0:
                    bb[:, [1, 3]] = th - bb[:, [3, 1]]
                bb[:, [0, 2]] += x1
                bb[:, [1, 3]] += y1
                B.append(bb), S.append(ss), C.append(cc)
        if not B:
            return Detections(np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, int))
        B, S, C = np.concatenate(B), np.concatenate(S), np.concatenate(C)
        if tta:  # a trace seen in only one of three views is likely noise: average support
            keep = ios_nms(B, S, C, iou_merge)
            support = np.array([self._support(B[k], C[k], B, C, iou_merge) for k in keep])
            S_keep = S[keep] * np.minimum(1.0, (support + 1) / (len(variants) + 1))
            B, S, C = B[keep], S_keep, C[keep]
            m = S >= conf
            B, S, C = B[m], S[m], C[m]
        else:
            keep = ios_nms(B, S, C, iou_merge)
            B, S, C = B[keep], S[keep], C[keep]
        if scale != 1.0:
            B = B / scale
        return Detections(B.astype(np.float32), S.astype(np.float32), C.astype(int))

    @staticmethod
    def _support(b, c, B, C, thr):
        m = C == c
        ix = np.clip(np.minimum(b[2], B[m, 2]) - np.maximum(b[0], B[m, 0]), 0, None)
        iy = np.clip(np.minimum(b[3], B[m, 3]) - np.maximum(b[1], B[m, 1]), 0, None)
        a1 = (b[2] - b[0]) * (b[3] - b[1])
        a2 = (B[m, 2] - B[m, 0]) * (B[m, 3] - B[m, 1])
        return int((ix * iy / np.maximum(np.minimum(a1, a2), 1e-6) >= thr).sum())


def draw(frame, dets, names, color_by_cls=((0, 255, 0), (0, 200, 255), (255, 120, 0))):
    vis = frame.copy()
    for b, s, c in zip(dets.boxes, dets.scores, dets.classes):
        x1, y1, x2, y2 = (int(round(v)) for v in b)
        col = color_by_cls[int(c) % len(color_by_cls)]
        cv2.rectangle(vis, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), col, 2)
        cv2.putText(vis, f"{names[int(c)][:6]} {s:.2f}", (x1, max(10, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    return vis

"""Tile grid + label clipping. Training, evaluation and inference share these functions
so that a tile seen at train time looks exactly like a tile seen on the robot."""

import numpy as np


def _starts(length, tile, step):
    if length <= tile:
        return [0]
    s = list(range(0, length - tile, step))
    s.append(length - tile)  # last tile flush with the edge instead of padding
    return sorted(set(s))


def tile_grid(w, h, tile=640, overlap=0.2):
    """Return list of (x1, y1, x2, y2) tiles covering a w x h image."""
    step = max(1, int(round(tile * (1 - overlap))))
    return [
        (x, y, min(x + tile, w), min(y + tile, h))
        for y in _starts(h, tile, step)
        for x in _starts(w, tile, step)
    ]


def clip_boxes_to_tile(boxes, tile_xyxy, min_visibility=0.6):
    """boxes (N,5) [cls,x1,y1,x2,y2] in image px -> boxes in tile px.

    A box cut by the tile border is kept only if >= min_visibility of its area remains;
    otherwise it is dropped (it will be whole in a neighbouring tile thanks to overlap).
    """
    if len(boxes) == 0:
        return np.zeros((0, 5), np.float32)
    tx1, ty1, tx2, ty2 = tile_xyxy
    b = boxes.copy()
    ix1 = np.clip(b[:, 1], tx1, tx2)
    iy1 = np.clip(b[:, 2], ty1, ty2)
    ix2 = np.clip(b[:, 3], tx1, tx2)
    iy2 = np.clip(b[:, 4], ty1, ty2)
    inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
    area = (b[:, 3] - b[:, 1]) * (b[:, 4] - b[:, 2])
    keep = (inter > 0) & (inter >= min_visibility * np.maximum(area, 1e-6))
    out = np.stack([b[:, 0], ix1 - tx1, iy1 - ty1, ix2 - tx1, iy2 - ty1], 1)[keep]
    return out.astype(np.float32)


def partially_cut(boxes, tile_xyxy, min_visibility=0.6):
    """True if some box is cut by this tile but too little remains to keep it as a label.
    Such tiles are poor negatives (a half dropping labelled as background)."""
    if len(boxes) == 0:
        return False
    tx1, ty1, tx2, ty2 = tile_xyxy
    ix1 = np.clip(boxes[:, 1], tx1, tx2)
    iy1 = np.clip(boxes[:, 2], ty1, ty2)
    ix2 = np.clip(boxes[:, 3], tx1, tx2)
    iy2 = np.clip(boxes[:, 4], ty1, ty2)
    inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
    area = (boxes[:, 3] - boxes[:, 1]) * (boxes[:, 4] - boxes[:, 2])
    return bool(((inter > 0) & (inter < min_visibility * area)).any())

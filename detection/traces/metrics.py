"""Full-frame metrics for tiny objects.

Tile-level mAP from ultralytics val is a training signal only. What matters on the farm is
how the *sliced* detector does on whole frames, so evaluate.py uses these functions:
  - AP at a loose IoU (0.3 default): a 2-px offset on a 8-px dropping already costs IoU 0.5
  - recall split by object size (px): tells whether the tiny end is the problem
  - FPPI (false positives per image): an operator tolerates a few, not dozens
  - image-level presence: "are there droppings in this frame?" - the FR-05 alarm decision
"""

import numpy as np

SIZE_BINS = [(0, 8), (8, 16), (16, 32), (32, 1e9)]


def iou_matrix(a, b):
    ix = np.clip(np.minimum(a[:, None, 2], b[None, :, 2]) - np.maximum(a[:, None, 0], b[None, :, 0]), 0, None)
    iy = np.clip(np.minimum(a[:, None, 3], b[None, :, 3]) - np.maximum(a[:, None, 1], b[None, :, 1]), 0, None)
    inter = ix * iy
    aa = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    ab = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (aa[:, None] + ab[None, :] - inter + 1e-9)


def drop_ignored(pred_boxes, pred_scores, pred_cls, ignore_boxes, ios_thr=0.5):
    """Remove predictions lying mostly inside an ignore region (GT class -1: clumps,
    unlabelable areas). They count as neither TP nor FP."""
    if len(ignore_boxes) == 0 or len(pred_boxes) == 0:
        return pred_boxes, pred_scores, pred_cls
    ix = np.clip(np.minimum(pred_boxes[:, None, 2], ignore_boxes[None, :, 2]) - np.maximum(pred_boxes[:, None, 0], ignore_boxes[None, :, 0]), 0, None)
    iy = np.clip(np.minimum(pred_boxes[:, None, 3], ignore_boxes[None, :, 3]) - np.maximum(pred_boxes[:, None, 1], ignore_boxes[None, :, 1]), 0, None)
    area = (pred_boxes[:, 2] - pred_boxes[:, 0]) * (pred_boxes[:, 3] - pred_boxes[:, 1])
    keep = ((ix * iy) / np.maximum(area[:, None], 1e-6)).max(1) < ios_thr
    return pred_boxes[keep], pred_scores[keep], pred_cls[keep]


def match_image(pred_boxes, pred_scores, gt_boxes, iou_thr):
    """Greedy by score. Returns (tp flags per pred sorted by score, scores sorted, matched gt idx per gt or -1)."""
    order = np.argsort(-pred_scores)
    pb, ps = pred_boxes[order], pred_scores[order]
    tp = np.zeros(len(pb), bool)
    gt_hit = -np.ones(len(gt_boxes), int)
    if len(pb) and len(gt_boxes):
        ious = iou_matrix(pb, gt_boxes)
        for i in range(len(pb)):
            j = np.argmax(np.where(gt_hit < 0, ious[i], -1))
            if gt_hit[j] < 0 and ious[i, j] >= iou_thr:
                tp[i] = True
                gt_hit[j] = i
    return tp, ps, gt_hit


def average_precision(tp, scores, n_gt):
    if n_gt == 0:
        return float("nan")
    if len(tp) == 0:
        return 0.0
    order = np.argsort(-scores)
    tp = tp[order]
    ctp, cfp = np.cumsum(tp), np.cumsum(~tp)
    rec = ctp / n_gt
    prec = ctp / np.maximum(ctp + cfp, 1)
    mrec = np.concatenate([[0], rec, [1]])
    mpre = np.concatenate([[1], prec, [0]])
    mpre = np.flip(np.maximum.accumulate(np.flip(mpre)))
    x = np.linspace(0, 1, 101)  # COCO-style 101-point interpolation
    return float(np.trapezoid(np.interp(x, mrec, mpre), x))


def evaluate(records, n_cls, iou_thr=0.3, conf_thr=0.25):
    """records: list of dicts {pred_boxes, pred_scores, pred_cls, gt_boxes, gt_cls}.

    Predictions should be produced at a low conf (e.g. 0.01) so AP sees the whole curve;
    conf_thr is the operating point for P/R/F1/FPPI.
    """
    out = {"per_class": {}, "n_images": len(records)}
    for c in range(n_cls):
        all_tp, all_s, n_gt = [], [], 0
        size_hit = {b: [0, 0] for b in SIZE_BINS}
        fp_op, tp_op = 0, 0
        for r in records:
            pm, gm = r["pred_cls"] == c, r["gt_cls"] == c
            gb = r["gt_boxes"][gm]
            tp, ps, gt_hit = match_image(r["pred_boxes"][pm], r["pred_scores"][pm], gb, iou_thr)
            all_tp.append(tp), all_s.append(ps)
            n_gt += len(gb)
            op = ps >= conf_thr
            tp_op += int((tp & op).sum())
            fp_op += int((~tp & op).sum())
            # size-binned recall at the operating point
            hit_op = np.array([h >= 0 and ps[h] >= conf_thr for h in gt_hit], bool)
            sizes = np.sqrt((gb[:, 2] - gb[:, 0]) * (gb[:, 3] - gb[:, 1])) if len(gb) else np.zeros(0)
            for lo, hi in SIZE_BINS:
                m = (sizes >= lo) & (sizes < hi)
                size_hit[(lo, hi)][0] += int(hit_op[m].sum())
                size_hit[(lo, hi)][1] += int(m.sum())
        tp_all = np.concatenate(all_tp) if all_tp else np.zeros(0, bool)
        s_all = np.concatenate(all_s) if all_s else np.zeros(0)
        p = tp_op / max(tp_op + fp_op, 1)
        rcl = tp_op / max(n_gt, 1)
        out["per_class"][c] = {
            "n_gt": n_gt,
            "AP": average_precision(tp_all, s_all, n_gt),
            "precision": p,
            "recall": rcl,
            "F1": 2 * p * rcl / max(p + rcl, 1e-9),
            "FPPI": fp_op / max(len(records), 1),
            "recall_by_size": {f"{int(lo)}-{'inf' if hi > 1e8 else int(hi)}px": (f"{h}/{n}" if n else "-")
                               for (lo, hi), (h, n) in size_hit.items()},
        }
    # image-level presence of class 0 (the alarm question)
    tp = fp = fn = tn = 0
    for r in records:
        has_gt = bool((r["gt_cls"] == 0).any())
        has_pred = bool(((r["pred_cls"] == 0) & (r["pred_scores"] >= conf_thr)).any())
        tp += has_gt and has_pred
        fp += (not has_gt) and has_pred
        fn += has_gt and not has_pred
        tn += (not has_gt) and not has_pred
    out["image_presence_cls0"] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn}
    return out


def best_conf(records, n_cls, iou_thr=0.3, cls=0, grid=np.arange(0.05, 0.96, 0.05)):
    """Operating threshold maximising F1 for one class (use on val, then fix it for test)."""
    best = (0.0, 0.25)
    for t in grid:
        f1 = evaluate(records, n_cls, iou_thr, float(t))["per_class"][cls]["F1"]
        if f1 > best[0]:
            best = (f1, float(t))
    return best[1], best[0]

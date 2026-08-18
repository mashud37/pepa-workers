"""Compute segmentation metrics: boundary precision, recall, and F1 split
into over- and under-segmentation, plus Pk and WindowDiff over a boundary
mask with window k derived from the gold segment count.
"""
from .predict import BOUNDARY, DROP


def _ends(labels: list) -> list:
    n = len(labels)
    return [1 if (i == n - 1 or labels[i + 1] in BOUNDARY) else 0 for i in range(n)]


def pk(ref: list, hyp: list, k: int) -> float:
    n = len(ref)
    if n <= k:
        return 0.0
    err = sum((sum(ref[i:i + k]) > 0) != (sum(hyp[i:i + k]) > 0) for i in range(n - k))
    return err / (n - k)


def windowdiff(ref: list, hyp: list, k: int) -> float:
    n = len(ref)
    if n <= k:
        return 0.0
    diff = sum(abs(sum(ref[i:i + k]) - sum(hyp[i:i + k])) > 0 for i in range(n - k))
    return diff / (n - k)


def _boundaries(labels: list) -> set:
    return {i for i in range(1, len(labels)) if labels[i] in BOUNDARY}


def score(gold: list, pred: list) -> dict:
    keep = [i for i, lab in enumerate(gold) if lab != DROP]
    junk = len(gold) - len(keep)
    gold = [gold[i] for i in keep]
    pred = [pred[i] for i in keep]
    g, p = _boundaries(gold), _boundaries(pred)
    tp, fp, fn = len(g & p), len(p - g), len(g - p)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    located = g & p
    ref_ends, hyp_ends = _ends(gold), _ends(pred)
    segs = sum(ref_ends) or 1
    k = max(2, round(len(ref_ends) / (2 * segs)))
    return {
        "lines": len(gold),
        "junk": junk,
        "gold_boundaries": len(g),
        "pred_boundaries": len(p),
        "precision": prec,
        "recall": rec,
        "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
        "over_seg": fp,
        "under_seg": fn,
        "type_acc": sum(gold[i] == pred[i] for i in located) / len(located) if located else 1.0,
        "pk": pk(ref_ends, hyp_ends, k),
        "windowdiff": windowdiff(ref_ends, hyp_ends, k),
    }

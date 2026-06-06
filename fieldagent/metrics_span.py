"""Tiny char-interval IoU used inside the pipeline's dedupe (no evals import cycle)."""
from __future__ import annotations


def iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    a0, a1 = a
    b0, b1 = b
    inter = max(0, min(a1, b1) - max(a0, b0))
    if inter == 0:
        return 0.0
    union = (a1 - a0) + (b1 - b0) - inter
    return inter / union if union > 0 else 0.0

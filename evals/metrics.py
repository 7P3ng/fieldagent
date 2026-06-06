"""Span-IoU detection metrics + agentic-lift / verifier ablation aggregation.

Pure functions, no model calls — so grading is unit-tested independently of any
live run, and identical code grades dry-run and live results. A prediction matches
a gold span iff the clause type is identical AND the half-open char-interval IoU
meets the threshold (CUAD-standard 0.5). Aggregation is micro (sum TP/FP/FN across
contracts); CIs are a seeded percentile bootstrap over contracts.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

Interval = tuple[int, int]


@dataclass(frozen=True)
class GoldSpan:
    clause_type: str
    start: int
    end: int


@dataclass(frozen=True)
class Prediction:
    clause_type: str
    start: int
    end: int


def span_iou(a: Interval, b: Interval) -> float:
    """Intersection-over-union of two half-open char intervals [start, end)."""
    a0, a1 = a
    b0, b1 = b
    inter = max(0, min(a1, b1) - max(a0, b0))
    if inter == 0:
        return 0.0
    union = (a1 - a0) + (b1 - b0) - inter
    return inter / union if union > 0 else 0.0


def match_contract(
    preds: list[Prediction], gold: list[GoldSpan], *, threshold: float = 0.5
) -> tuple[int, int, int]:
    """Greedy 1-gold-to-1-pred matching within one contract.

    Returns ``(tp, fp, fn)``. A gold span can be claimed by at most one prediction;
    we match the highest-IoU eligible (pred, gold) pairs first (greedy), so two
    predictions overlapping one gold yield 1 TP + 1 FP, not 2 TP.
    """
    pairs: list[tuple[float, int, int]] = []
    for pi, p in enumerate(preds):
        for gi, g in enumerate(gold):
            if p.clause_type != g.clause_type:
                continue
            iou = span_iou((p.start, p.end), (g.start, g.end))
            if iou >= threshold:
                pairs.append((iou, pi, gi))
    pairs.sort(reverse=True)  # highest IoU first
    used_p: set[int] = set()
    used_g: set[int] = set()
    tp = 0
    for _iou, pi, gi in pairs:
        if pi in used_p or gi in used_g:
            continue
        used_p.add(pi)
        used_g.add(gi)
        tp += 1
    fp = len(preds) - len(used_p)
    fn = len(gold) - len(used_g)
    return tp, fp, fn


def prf1(*, tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Precision, recall, F1 from counts. Zero-safe (returns 0.0 where undefined)."""
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = (2 * p * r / (p + r)) if (p + r) else 0.0
    return p, r, f


def _f1_from_triples(triples: list[tuple[int, int, int]]) -> float:
    tp = sum(t[0] for t in triples)
    fp = sum(t[1] for t in triples)
    fn = sum(t[2] for t in triples)
    return prf1(tp=tp, fp=fp, fn=fn)[2]


def bootstrap_f1_ci(
    per_contract: list[tuple[int, int, int]],
    *, iters: int = 2000, seed: int = 0, alpha: float = 0.05,
) -> tuple[float, float]:
    """Seeded percentile bootstrap 95% CI for micro-F1, resampling contracts.

    Each element of ``per_contract`` is that contract's ``(tp, fp, fn)``. We
    resample contracts with replacement, recompute micro-F1, and take percentiles.
    Reuses the seeded-RNG idiom of ``evals/grade.bootstrap_ci`` (extended from a
    mean-of-0/1 to a recomputed-F1 statistic).
    """
    if not per_contract:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(per_contract)
    f1s = sorted(
        _f1_from_triples([per_contract[rng.randrange(n)] for _ in range(n)])
        for _ in range(iters)
    )
    lo = f1s[int((alpha / 2) * iters)]
    hi = f1s[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (round(lo, 4), round(hi, 4))

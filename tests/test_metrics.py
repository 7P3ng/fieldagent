"""Span-IoU grading — the heart of both headline claims. No model calls.

A predicted finding (clause_type, start, end) matches a gold span iff the clause
type is identical AND the char-interval IoU >= threshold (0.5). These tests pin
the metric's contract before any pipeline exists.
"""
from __future__ import annotations

from evals.metrics import (
    GoldSpan,
    Prediction,
    bootstrap_f1_ci,
    match_contract,
    prf1,
    span_iou,
)


def test_iou_identical_is_one():
    assert span_iou((10, 20), (10, 20)) == 1.0


def test_iou_disjoint_is_zero():
    assert span_iou((0, 10), (20, 30)) == 0.0


def test_iou_half_overlap():
    # pred [0,10), gold [5,15): inter=5, union=15 -> 1/3
    assert abs(span_iou((0, 10), (5, 15)) - (5 / 15)) < 1e-9


def test_iou_touching_is_zero():
    # half-open intervals that only touch share no length
    assert span_iou((0, 10), (10, 20)) == 0.0


def test_match_type_mismatch_never_matches():
    preds = [Prediction("Cap On Liability", 0, 100)]
    gold = [GoldSpan("Non-Compete", 0, 100)]
    tp, fp, fn = match_contract(preds, gold, threshold=0.5)
    assert (tp, fp, fn) == (0, 1, 1)


def test_match_perfect():
    preds = [Prediction("Renewal Term", 10, 30)]
    gold = [GoldSpan("Renewal Term", 10, 30)]
    tp, fp, fn = match_contract(preds, gold, threshold=0.5)
    assert (tp, fp, fn) == (1, 0, 0)


def test_match_below_threshold_is_miss():
    # IoU = 1/3 < 0.5 -> not a match: 1 FP + 1 FN
    preds = [Prediction("Exclusivity", 0, 10)]
    gold = [GoldSpan("Exclusivity", 5, 15)]
    tp, fp, fn = match_contract(preds, gold, threshold=0.5)
    assert (tp, fp, fn) == (0, 1, 1)


def test_match_one_gold_one_pred_greedy():
    # two preds overlap the same gold; only one can match it
    preds = [Prediction("Audit Rights", 0, 20), Prediction("Audit Rights", 1, 21)]
    gold = [GoldSpan("Audit Rights", 0, 20)]
    tp, fp, fn = match_contract(preds, gold, threshold=0.5)
    assert tp == 1 and fp == 1 and fn == 0


def test_prf1_basic():
    p, r, f = prf1(tp=8, fp=2, fn=2)
    assert abs(p - 0.8) < 1e-9 and abs(r - 0.8) < 1e-9 and abs(f - 0.8) < 1e-9


def test_prf1_zero_safe():
    assert prf1(tp=0, fp=0, fn=0) == (0.0, 0.0, 0.0)


def test_bootstrap_f1_ci_is_seeded_and_bounded():
    # per-contract (tp,fp,fn) triples; CI must be within [0,1] and lo<=hi, reproducible
    per_contract = [(5, 1, 1), (3, 0, 2), (4, 2, 0), (6, 1, 1)]
    lo1, hi1 = bootstrap_f1_ci(per_contract, iters=500, seed=0)
    lo2, hi2 = bootstrap_f1_ci(per_contract, iters=500, seed=0)
    assert (lo1, hi1) == (lo2, hi2)  # seeded reproducibility
    assert 0.0 <= lo1 <= hi1 <= 1.0

"""Offline reproduction guard: the committed headline numbers must be exactly
recomputable from the committed per-contract (tp,fp,fn) triples — pure functions,
no dataset, no model. If results/ is absent (pre-live-run), the test skips.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.metrics import bootstrap_f1_ci, prf1

_ROOT = Path(__file__).resolve().parent.parent
_METRICS = _ROOT / "evals" / "results" / "metrics.json"
_PER = _ROOT / "evals" / "results" / "per_contract.json"


@pytest.mark.skipif(not (_METRICS.exists() and _PER.exists()),
                    reason="no committed results yet (run the live eval first)")
def test_headline_reproduces_from_committed_triples():
    metrics = json.loads(_METRICS.read_text())
    per = json.loads(_PER.read_text())

    def micro_f1(arm: str) -> float:
        triples = [tuple(t) for t in per[arm]]
        tp = sum(t[0] for t in triples)
        fp = sum(t[1] for t in triples)
        fn = sum(t[2] for t in triples)
        return prf1(tp=tp, fp=fp, fn=fn)[2]

    for arm in ("keyword", "single_shot", "pipeline_no_verifier", "pipeline_full"):
        recomputed = round(micro_f1(arm), 4)
        committed = metrics["arms"][arm]["f1"]
        assert abs(recomputed - committed) < 1e-9, f"{arm}: {recomputed} != {committed}"

    # lift + verifier contribution reproduce
    full = micro_f1("pipeline_full")
    assert abs(round(full - micro_f1("single_shot"), 4) - metrics["agentic_lift_f1"]) < 1e-9
    assert abs(round(full - micro_f1("pipeline_no_verifier"), 4)
               - metrics["verifier_contribution_f1"]) < 1e-9

    # CI reproduces (seeded bootstrap)
    triples = [tuple(t) for t in per["pipeline_full"]]
    lo, hi = bootstrap_f1_ci(triples, iters=2000, seed=0)
    assert [lo, hi] == metrics["arms"]["pipeline_full"]["ci95"]

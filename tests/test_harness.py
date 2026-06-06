"""Eval-harness logic on SYNTHETIC cases (no real CUAD needed). Covers the four
arms, the degraded-run guard, and the cost gate — all with FakeClient, zero cost."""
from __future__ import annotations

import json

import pytest

from core.model_client import FakeClient
from evals.harness import (
    ContractCase,
    DegradedRunError,
    estimate_cost_usd,
    evaluate,
)
from evals.metrics import GoldSpan

# Two tiny synthetic contracts, each with one unambiguous clause.
CASES = [
    ContractCase(
        doc_id="syn-1",
        text=("Preamble. " * 30 +
              "Either party may terminate for convenience on 30 days notice. " +
              "Tail boilerplate. " * 30),
        gold=[GoldSpan("Termination For Convenience", -1, -1)],  # offsets filled below
    ),
    ContractCase(
        doc_id="syn-2",
        text=("Recitals. " * 30 +
              "Distributor is appointed on an exclusive basis in the Territory. " +
              "More tail. " * 30),
        gold=[GoldSpan("Exclusivity", -1, -1)],
    ),
]
# fill gold offsets to the real location of the clause in each synthetic text
_Q1 = "terminate for convenience on 30 days notice"
_Q2 = "exclusive basis in the Territory"
CASES[0].gold[0] = GoldSpan("Termination For Convenience", CASES[0].text.find(_Q1), CASES[0].text.find(_Q1) + len(_Q1))
CASES[1].gold[0] = GoldSpan("Exclusivity", CASES[1].text.find(_Q2), CASES[1].text.find(_Q2) + len(_Q2))


def _good_responder(model, system, messages, max_tokens):
    user = messages[-1]["content"]
    if "FLAGGED QUOTE" in user:
        return json.dumps({"verdict": "keep", "confidence": 0.95, "reason": "ok"})
    out = []
    if _Q1 in user:
        out.append({"clause_type": "Termination For Convenience", "quote": _Q1, "why": "exit at will"})
    if _Q2 in user:
        out.append({"clause_type": "Exclusivity", "quote": _Q2, "why": "exclusive"})
    return json.dumps({"findings": out})


def _empty_responder(model, system, messages, max_tokens):
    if "FLAGGED QUOTE" in messages[-1]["content"]:
        return json.dumps({"verdict": "drop", "confidence": 0.9, "reason": "no"})
    return json.dumps({"findings": []})


def test_evaluate_runs_four_arms_and_computes_lift():
    res = evaluate(CASES, FakeClient(_good_responder), model="deepseek-chat",
                   window=900, overlap=200, concurrency=2)
    arms = res["arms"]
    assert set(arms) == {"keyword", "single_shot", "pipeline_no_verifier", "pipeline_full"}
    # full pipeline should recover both gold clauses -> recall 1.0, high F1
    assert arms["pipeline_full"]["recall"] == 1.0
    assert arms["pipeline_full"]["f1"] > 0.0
    # lift fields present and numeric
    assert "agentic_lift_f1" in res and "verifier_contribution_f1" in res
    assert isinstance(res["agentic_lift_f1"], float)


def test_degraded_guard_aborts_on_zero_extractions():
    with pytest.raises(DegradedRunError):
        evaluate(CASES, FakeClient(_empty_responder), model="deepseek-chat",
                 window=900, overlap=200, concurrency=2)


def test_cost_estimate_is_positive_and_scales():
    one = estimate_cost_usd(CASES[:1], model="deepseek-chat")
    two = estimate_cost_usd(CASES, model="deepseek-chat")
    assert two.usd > one.usd > 0.0
    assert two.n_calls > one.n_calls


def test_cost_gate_refuses_over_max():
    from evals.harness import CostGateError, check_cost_gate, estimate_cost_usd
    est = estimate_cost_usd(CASES, model="deepseek-chat")
    # an absurdly low cap must trip the gate
    with pytest.raises(CostGateError):
        check_cost_gate(est, 0.0)
    # a generous cap passes
    check_cost_gate(est, 1000.0)

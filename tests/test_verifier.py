"""Skeptic verification pass — the false-positive cutter that drives agentic lift."""
from __future__ import annotations

import json

from core.model_client import FakeClient
from fieldagent.types import Candidate
from fieldagent.verifier import verify_candidate, verify_candidates


def _cand():
    return Candidate("Exclusivity", "exclusive rights in the Territory", 100, 132,
                     rationale="exclusive appointment", chunk_index=0)


def _client(verdict, confidence):
    payload = {"verdict": verdict, "confidence": confidence, "reason": "test"}
    return FakeClient(lambda m, s, msg, mt: json.dumps(payload))


def test_keep_retains_candidate():
    keep, conf, _ = verify_candidate(_client("keep", 0.9), _cand(), "...context...", model="deepseek-chat")
    assert keep is True and conf == 0.9


def test_drop_removes_candidate():
    keep, _, _ = verify_candidate(_client("drop", 0.8), _cand(), "...context...", model="deepseek-chat")
    assert keep is False


def test_low_confidence_keep_is_dropped():
    # verdict 'keep' but confidence below the floor -> not kept
    keep, _, _ = verify_candidate(_client("keep", 0.2), _cand(), "ctx", model="deepseek-chat",
                                  min_confidence=0.5)
    assert keep is False


def test_malformed_verifier_output_is_conservative_drop():
    client = FakeClient(lambda m, s, msg, mt: "not json")
    keep, _, _ = verify_candidate(client, _cand(), "ctx", model="deepseek-chat")
    assert keep is False


def test_verify_candidates_filters_list():
    kept = verify_candidates(_client("keep", 0.9), [_cand(), _cand()], "full contract text",
                             model="deepseek-chat", concurrency=2)
    assert len(kept) == 2
    dropped = verify_candidates(_client("drop", 0.9), [_cand()], "full contract text",
                               model="deepseek-chat", concurrency=2)
    assert dropped == []

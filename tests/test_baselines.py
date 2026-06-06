"""Baselines: keyword/regex floor + naive single-shot LLM (the agentic-lift comparators)."""
from __future__ import annotations

import json

from core.model_client import FakeClient
from fieldagent.baselines import keyword_baseline, single_shot


def test_keyword_flags_known_trigger():
    text = ("This Agreement sets out the terms. Neither party shall compete with the other in a "
            "non-compete arrangement for two years. The remainder is boilerplate.")
    cands = keyword_baseline(text)
    types = {c.clause_type for c in cands}
    assert "Non-Compete" in types
    nc = next(c for c in cands if c.clause_type == "Non-Compete")
    # the flagged span sits inside the document and contains the trigger
    assert "non-compete" in text[nc.start:nc.end].lower()


def test_keyword_finds_exclusivity_and_audit():
    text = ("Vendor is appointed on an exclusive basis. Customer has the right to audit Vendor's "
            "records once per year.")
    types = {c.clause_type for c in keyword_baseline(text)}
    assert "Exclusivity" in types
    assert "Audit Rights" in types


def test_keyword_clean_text_no_flags():
    text = "The parties agree to meet quarterly and exchange friendly greetings."
    assert keyword_baseline(text) == []


def test_single_shot_parses_findings_with_offsets():
    full = "Intro. " * 50 + "The Distributor shall have exclusive rights in the Territory."
    payload = {"findings": [{
        "clause_type": "Exclusivity",
        "quote": "exclusive rights in the Territory",
        "why": "exclusive appointment",
    }]}
    client = FakeClient(lambda m, s, msg, mt: json.dumps(payload))
    cands = single_shot(client, full, model="deepseek-chat")
    assert len(cands) == 1
    c = cands[0]
    assert c.clause_type == "Exclusivity"
    assert full[c.start:c.end] == "exclusive rights in the Territory"

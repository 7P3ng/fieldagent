"""End-to-end pipeline on FakeClient: chunk -> extract -> verify -> dedupe -> Findings, traced."""
from __future__ import annotations

import json

from core.model_client import FakeClient
from core.tracing import TraceStore
from fieldagent.pipeline import analyze

# A contract with one clear Termination-for-Convenience clause, padded to force >1 chunk.
CONTRACT = (
    "MASTER SERVICES AGREEMENT. " + "Background recitals and definitions. " * 80 +
    "Either party may terminate this Agreement for convenience upon thirty (30) days written notice. " +
    "Boilerplate notices follow. " * 80
)
QUOTE = "terminate this Agreement for convenience upon thirty (30) days written notice"


def _responder(model, system, messages, max_tokens):
    user = messages[-1]["content"]
    # Route by user-prompt content (robust): the verifier prompt carries "FLAGGED QUOTE",
    # the extractor/single-shot prompts carry the taxonomy header "CLAUSE TYPES".
    if "FLAGGED QUOTE" in user:
        return json.dumps({"verdict": "keep", "confidence": 0.95, "reason": "clear TfC"})
    if QUOTE in user:
        return json.dumps({"findings": [{
            "clause_type": "Termination For Convenience", "quote": QUOTE, "why": "exit at will"}]})
    return json.dumps({"findings": []})


def test_pipeline_emits_structured_findings():
    client = FakeClient(_responder)
    findings = analyze(client, CONTRACT, model="deepseek-chat", window=1500, overlap=300)
    tfc = [f for f in findings if f.clause_type == "Termination For Convenience"]
    assert len(tfc) == 1, f"expected 1 deduped TfC finding, got {len(findings)}"
    f = tfc[0]
    assert CONTRACT[f.start:f.end] == QUOTE          # correct global offsets
    assert f.severity == "high"                       # from taxonomy
    assert len(f.risk_note) > 20                      # plain-English risk
    assert f.verified is True and f.confidence >= 0.9


def test_pipeline_dedupes_overlapping_candidates_across_chunks():
    # the clause sits in the overlap region -> extracted from 2 chunks -> must dedupe to 1
    client = FakeClient(_responder)
    findings = analyze(client, CONTRACT, model="deepseek-chat", window=1500, overlap=300)
    spans = [(f.start, f.end) for f in findings if f.clause_type == "Termination For Convenience"]
    assert len(spans) == 1


def test_pipeline_is_fully_traced():
    store = TraceStore(":memory:")
    run_id = store.new_run("test")
    client = FakeClient(_responder)
    analyze(client, CONTRACT, model="deepseek-chat", window=1500, overlap=300,
            trace=store, run_id=run_id)
    spans = store.query(run_id)
    assert len(spans) > 0
    # both extract and verify phases produced spans with cost recorded
    names = {s["name"] for s in spans}
    assert any("extract" in n for n in names)
    assert any("verify" in n for n in names)


def test_pipeline_without_verifier_skips_verification():
    client = FakeClient(_responder)
    findings = analyze(client, CONTRACT, model="deepseek-chat", window=1500, overlap=300,
                       verify=False)
    # still finds the clause, but marked unverified
    tfc = [f for f in findings if f.clause_type == "Termination For Convenience"]
    assert len(tfc) == 1
    assert tfc[0].verified is False

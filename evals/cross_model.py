"""Grade the Claude cross-model validation (subagent-produced, plan auth).

Reads the raw model responses in fixtures/claude_resp/ (single-shot + per-chunk
extraction for the 8-contract subset), locates spans, and grades single-shot vs
chunked extraction with the SAME span-IoU metric as the DeepSeek harness. This
isolates the chunking lever on a second model — no truncation (Claude finished
every response), no DeepSeek dependency.
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.metrics import Prediction, bootstrap_f1_ci, match_contract, prf1
from evals.run_eval import load_heldout
from fieldagent import baselines
from fieldagent.chunker import chunk_text
from fieldagent.clauses import RISK_TYPES
from fieldagent.extractor import _parse_json_obj, locate_span

N, WINDOW, OVERLAP = 8, 9000, 1200
RESP = Path(__file__).parent / "fixtures" / "claude_resp"
_RISK = set(RISK_TYPES)


def _preds_single_shot(text: str, raw: str) -> list[Prediction]:
    body = text[: baselines._SINGLE_SHOT_BUDGET]
    obj = _parse_json_obj(raw) or {}
    out = []
    for f in obj.get("findings", []):
        if not isinstance(f, dict):
            continue
        ct, q = f.get("clause_type"), f.get("quote")
        if ct not in _RISK or not isinstance(q, str):
            continue
        loc = locate_span(body, q)
        if loc:
            out.append(Prediction(ct, loc[0], loc[1]))
    return out


def _preds_chunked(text: str, raws: list[str]) -> list[Prediction]:
    chunks = chunk_text(text, window=WINDOW, overlap=OVERLAP)
    cands: list[Prediction] = []
    for ch, raw in zip(chunks, raws, strict=False):
        obj = _parse_json_obj(raw) or {}
        for f in obj.get("findings", []):
            if not isinstance(f, dict):
                continue
            ct, q = f.get("clause_type"), f.get("quote")
            if ct not in _RISK or not isinstance(q, str):
                continue
            loc = locate_span(ch.text, q)
            if loc:
                cands.append(Prediction(ct, ch.start + loc[0], ch.start + loc[1]))
    # dedupe same-type overlaps
    cands.sort(key=lambda p: (p.clause_type, p.start))
    kept: list[Prediction] = []
    for c in cands:
        if any(k.clause_type == c.clause_type and c.start < k.end and k.start < c.end for k in kept):
            continue
        kept.append(c)
    return kept


def _grade(cases, preds_per):
    per = [match_contract(p, c.gold, threshold=0.5) for c, p in zip(cases, preds_per, strict=True)]
    tp = sum(t for t, _, _ in per)
    fp = sum(f for _, f, _ in per)
    fn = sum(f for _, _, f in per)
    p, r, f1 = prf1(tp=tp, fp=fp, fn=fn)
    return {"p": round(p, 3), "r": round(r, 3), "f1": round(f1, 4),
            "ci": bootstrap_f1_ci(per, iters=2000, seed=0), "tp": tp, "fp": fp, "fn": fn}


def main() -> int:
    cases = sorted(load_heldout(), key=lambda c: len(c.text))[:N]
    ss_preds, ck_preds = [], []
    n_ss_find = 0
    for i, c in enumerate(cases):
        ss_raw = (RESP / f"resp_{i}_ss.json").read_text()
        n_chunks = len(chunk_text(c.text, window=WINDOW, overlap=OVERLAP))
        ck_raws = [(RESP / f"resp_{i}_ex_{j}.json").read_text() for j in range(n_chunks)]
        sp = _preds_single_shot(c.text, ss_raw)
        n_ss_find += len(sp)
        ss_preds.append(sp)
        ck_preds.append(_preds_chunked(c.text, ck_raws))
    ss = _grade(cases, ss_preds)
    ck = _grade(cases, ck_preds)
    result = {
        "model": "claude-sonnet-4-6", "n_contracts": N, "auth": "Max-20x plan (subagents, no claude -p)",
        "gold_spans": sum(len(c.gold) for c in cases),
        "single_shot": ss, "pipeline_chunked_no_verifier": ck,
        "chunking_lift_f1": round(ck["f1"] - ss["f1"], 4),
        "single_shot_findings_located": n_ss_find,
    }
    (Path(__file__).parent / "results" / "cross_model_claude.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

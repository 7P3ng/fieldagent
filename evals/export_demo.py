"""Generate the static demo dataset (web/src/lib/data.json) — ZERO cost.

Replays the recorded fixtures (RecordedClient) over a handful of held-out
contracts to produce real pipeline findings, marks gold-vs-predicted matches,
redacts party names + dollar figures (length-preserving so char offsets stay
valid for inline highlighting), and bundles the committed metrics. Never makes a
paid call.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.model_client import RecordedClient
from evals.metrics import span_iou
from evals.run_eval import _RAW, OVERLAP, WINDOW, load_heldout
from fieldagent.pipeline import analyze

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "evals" / "fixtures" / "deepseek_fixtures.json"
_METRICS = _ROOT / "evals" / "results" / "metrics.json"
_OUT = _ROOT / "web" / "src" / "lib" / "data.json"

# Curated for variety + clear findings (agreement-type diversity). Title substrings.
DEMO_PICKS = [
    "LUCIDINC", "IVILLAGEINC", "MERITLIFEINSURANCECO",
    "SPARKLINGSPRINGWATERHOLDINGSLTD", "MEDALISTDIVERSIFIEDREIT", "TUNIUCORP",
]
_DOLLAR = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")


def agreement_type(title: str) -> str:
    t = title.upper()
    for kw, label in [
        ("DISTRIBUTOR", "Distributor"), ("RESELLER", "Reseller"), ("SPONSORSHIP", "Sponsorship"),
        ("CONSULTING", "Consulting"), ("SERVICES", "Services"), ("HOSTING", "Hosting"),
        ("SOFTWARE", "Software"), ("ENDORSEMENT", "Endorsement"), ("COOPERATION", "Cooperation"),
        ("STRATEGIC ALLIANCE", "Strategic Alliance"), ("OUTSOURCING", "Outsourcing"),
        ("LICENSE", "License"), ("DEVELOPMENT", "Development"), ("TRANSPORTATION", "Transportation"),
        ("MASTER", "Master Services"), ("PROMOTION", "Promotion"),
    ]:
        if kw in t:
            return label
    return "Agreement"


def redact(text: str, parties: list[str]) -> str:
    """Length-preserving redaction of dollar figures + party names → █ blocks."""
    chars = list(text)

    def blank(s: int, e: int) -> None:
        for i in range(s, min(e, len(chars))):
            if chars[i] not in " \n\t":
                chars[i] = "█"

    for m in _DOLLAR.finditer(text):
        blank(m.start(), m.end())
    for p in parties:
        p = p.strip()
        if len(p) < 4:
            continue
        for m in re.finditer(re.escape(p), text):
            blank(m.start(), m.end())
    return "".join(chars)


def main() -> int:
    if not _FIX.exists() or not _METRICS.exists():
        print(f"missing {_FIX} or {_METRICS} — run a live eval first.")
        return 1
    fixtures = json.loads(_FIX.read_text())
    metrics = json.loads(_METRICS.read_text())
    client = RecordedClient(fixtures, strict=True)
    cases = {c.doc_id: c for c in load_heldout()}
    raw = {d["title"]: d for d in json.loads(_RAW.read_text())["data"]}

    picks = []
    for sub in DEMO_PICKS:
        match = next((cid for cid in cases if sub in cid), None)
        if match:
            picks.append(match)

    contracts = []
    for cid in picks:
        case = cases[cid]
        findings = analyze(client, case.text, model="deepseek", window=WINDOW, overlap=OVERLAP,
                           verify=True, concurrency=1)
        # match findings vs gold (per type, IoU >= 0.5)
        gold_by_type: dict[str, list] = {}
        for g in case.gold:
            gold_by_type.setdefault(g.clause_type, []).append(g)
        out_findings = []
        matched_gold_ids = set()
        for f in findings:
            best = 0.0
            best_g = None
            for g in gold_by_type.get(f.clause_type, []):
                v = span_iou((f.start, f.end), (g.start, g.end))
                if v > best:
                    best, best_g = v, g
            matched = best >= 0.5
            if matched and best_g is not None:
                matched_gold_ids.add(id(best_g))
            out_findings.append({
                "clause_type": f.clause_type, "span_text": f.span_text,
                "start": f.start, "end": f.end, "severity": f.severity,
                "risk_note": f.risk_note, "confidence": round(f.confidence, 3),
                "rationale": f.rationale, "matched_gold": matched,
            })
        gold_out = [{"clause_type": g.clause_type, "start": g.start, "end": g.end,
                     "matched": id(g) in matched_gold_ids} for g in case.gold]
        # parties for redaction
        parties: list[str] = []
        for qa in raw[cid]["paragraphs"][0]["qas"]:
            if qa["id"].endswith("__Parties") and qa.get("answers"):
                parties += [a["text"] for a in qa["answers"]]
        red = redact(case.text, parties)
        contracts.append({
            "doc_id": cid,
            "title": cid.split("-EX-")[0].replace("_", " ")[:70],
            "agreement_type": agreement_type(cid),
            "text": red,
            "findings": out_findings,
            "gold_spans": gold_out,
        })

    arms = metrics["arms"]
    full = arms["pipeline_full"]
    results = {
        "contracts_processed": metrics["meta"]["contracts_processed"],
        "n_clause_types": 15,
        "iou_threshold": metrics["meta"]["iou_threshold"],
        "model": metrics["meta"]["model"],
        "total_gold_spans": sum(len(c.gold) for c in cases.values()),
        "arms": {k: {"precision": arms[k]["precision"], "recall": arms[k]["recall"],
                     "f1": arms[k]["f1"], "ci95": arms[k]["ci95"]} for k in arms},
        "agentic_lift_f1": metrics["agentic_lift_f1"],
        "verifier_contribution_f1": metrics["verifier_contribution_f1"],
        "iou_threshold_sweep": metrics["iou_threshold_sweep"],
        "per_type": sorted(
            [{"clause_type": t, **{k: v[k] for k in ("gold", "precision", "recall", "f1")}}
             for t, v in full["per_type"].items()],
            key=lambda x: -x["gold"]),
    }
    xm_path = _ROOT / "evals" / "results" / "cross_model_claude.json"
    cross_model = json.loads(xm_path.read_text()) if xm_path.exists() else None
    data = {"generated_at": metrics["meta"].get("model", ""), "results": results,
            "contracts": contracts, "cross_model": cross_model}
    _OUT.write_text(json.dumps(data, indent=1))
    print(f"wrote {_OUT}: {len(contracts)} contracts, "
          f"{sum(len(c['findings']) for c in contracts)} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

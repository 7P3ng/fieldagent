"""FieldAgent eval CLI.

Default = DRY-RUN: replays committed fixtures through RecordedClient (zero paid
calls) and reproduces the headline tables. A LIVE run requires FIELDAGENT_LIVE=1,
prints a cost estimate BEFORE the first paid call, and refuses to exceed
FIELDAGENT_MAX_USD (default $1.00). After a live run, every raw response is
serialized to evals/fixtures/ so all later iterations replay for free.

    python evals/run_eval.py                 # dry-run (needs fixtures + CUAD fetched)
    FIELDAGENT_LIVE=1 python evals/run_eval.py   # one live DeepSeek run (cost-gated)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from core.model_client import ModelClient, RecordedClient
from core.tracing import TraceStore
from evals.harness import (
    ContractCase,
    RecordingClient,
    check_cost_gate,
    estimate_cost_usd,
    evaluate,
)
from evals.metrics import GoldSpan

_ROOT = Path(__file__).resolve().parent.parent
_BENCH = _ROOT / "evals" / "benchmark"
_RAW = _BENCH / "raw" / "CUAD_v1.json"
_GOLD = _BENCH / "heldout_gold.json"
_FIXTURES = _ROOT / "evals" / "fixtures"
_RESULTS = _ROOT / "evals" / "results"

WINDOW = 6000
OVERLAP = 800


def load_heldout() -> list[ContractCase]:
    """Reconstitute held-out contracts from gold offsets + the fetched raw CUAD.

    Verifies each gold span's 8-char text hash against the fetched text, so a wrong
    dataset version (shifted offsets) fails loudly instead of grading garbage.
    """
    if not _RAW.exists():
        raise FileNotFoundError(
            f"{_RAW} missing — run `python evals/benchmark/fetch_cuad.py` first "
            "(raw CUAD is gitignored; data hygiene)."
        )
    gold = json.loads(_GOLD.read_text())
    raw = json.loads(_RAW.read_text())
    ctx_by_title = {doc["title"]: doc["paragraphs"][0]["context"] for doc in raw["data"]}
    cases: list[ContractCase] = []
    for c in gold["contracts"]:
        title = c["doc_id"]
        text = ctx_by_title[title]
        spans: list[GoldSpan] = []
        for g in c["gold_spans"]:
            start, end = g["start"], g["end"]
            got = hashlib.sha256(text[start:end].encode()).hexdigest()[:8]
            if got != g["text_sha8"]:
                raise ValueError(
                    f"gold integrity check failed for {title} [{start}:{end}] "
                    f"({g['clause_type']}): expected {g['text_sha8']} got {got}. "
                    "Wrong CUAD version?"
                )
            spans.append(GoldSpan(g["clause_type"], start, end))
        cases.append(ContractCase(doc_id=title, text=text, gold=spans))
    return cases


def _fixture_path(target: str) -> Path:
    return _FIXTURES / f"{target}_fixtures.json"


def _load_fixtures(target: str) -> dict[str, Any]:
    p = _fixture_path(target)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} missing — no recorded fixtures for dry-run. Run a live eval first "
            "(FIELDAGENT_LIVE=1) or fetch committed fixtures."
        )
    return json.loads(p.read_text())


def _build_live_client(target: str) -> ModelClient:
    if target == "deepseek":
        from core.deepseek_client import DeepSeekClient
        return DeepSeekClient()
    if target == "anthropic":
        from core.anthropic_client import AnthropicClient
        return AnthropicClient()
    raise ValueError(f"unknown target {target!r}")


def _write_results(target: str, results: dict[str, Any]) -> None:
    _RESULTS.mkdir(parents=True, exist_ok=True)
    (_RESULTS / "metrics.json").write_text(json.dumps(results, indent=2))
    # per-contract triples for offline reproduction tests
    per = {a: results["arms"][a]["per_contract"] for a in results["arms"]}
    (_RESULTS / "per_contract.json").write_text(json.dumps(per, indent=1))
    (_RESULTS / "metrics.md").write_text(render_markdown(results))


def render_markdown(r: dict[str, Any]) -> str:
    arms = r["arms"]
    meta = r["meta"]

    def row(a: str, label: str) -> str:
        d = arms[a]
        lo, hi = d["ci95"]
        return (f"| {label} | {d['precision']:.3f} | {d['recall']:.3f} | "
                f"**{d['f1']:.3f}** | [{lo:.3f}, {hi:.3f}] |")

    lines = [
        "# FieldAgent — detection results",
        "",
        f"Held-out CUAD contracts: **{meta['contracts_processed']}** · "
        f"clause types: **15** · IoU threshold: **{meta['iou_threshold']}** · "
        f"model: `{meta['model']}`",
        "",
        "| Arm | Precision | Recall | F1 | 95% CI (F1) |",
        "|---|---|---|---|---|",
        row("keyword", "Keyword/regex floor"),
        row("single_shot", "Single-shot LLM (baseline)"),
        row("pipeline_no_verifier", "Pipeline − verifier (chunked)"),
        row("pipeline_full", "**Pipeline (full, agentic)**"),
        "",
        f"**Agentic lift** (full − single-shot): **+{r['agentic_lift_f1']:.3f} F1**  ·  "
        f"**Verifier contribution** (full − no-verifier): **+{r['verifier_contribution_f1']:.3f} F1**",
        "",
        "## Per-clause-type F1 (full pipeline)",
        "",
        "| Clause type | Gold | P | R | F1 |",
        "|---|---|---|---|---|",
    ]
    for t, d in sorted(arms["pipeline_full"]["per_type"].items(),
                       key=lambda kv: -kv[1]["gold"]):
        lines.append(f"| {t} | {d['gold']} | {d['precision']:.2f} | "
                     f"{d['recall']:.2f} | {d['f1']:.2f} |")
    sweep = r.get("iou_threshold_sweep")
    if sweep:
        lines += ["", "## IoU-threshold sensitivity (F1)", "",
                  "| IoU | Single-shot | Pipeline (full) |", "|---|---|---|"]
        for thr in ("0.1", "0.3", "0.5", "0.7"):
            sv = sweep[thr]
            lines.append(f"| {thr} | {sv['single_shot']:.3f} | {sv['pipeline_full']:.3f} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FieldAgent eval harness")
    ap.add_argument("--target", default="deepseek", choices=["deepseek", "anthropic"])
    ap.add_argument("--max-usd", type=float,
                    default=float(os.environ.get("FIELDAGENT_MAX_USD", "1.00")))
    ap.add_argument("--concurrency", type=int,
                    default=int(os.environ.get("FIELDAGENT_EVAL_CONCURRENCY", "4")))
    args = ap.parse_args(argv)
    concurrency = max(1, min(8, args.concurrency))  # semaphore: default 4, hard max 8

    live = os.environ.get("FIELDAGENT_LIVE") == "1"
    cases = load_heldout()
    print(f"Loaded {len(cases)} held-out contracts "
          f"({sum(len(c.gold) for c in cases)} gold spans).", file=sys.stderr)

    store = TraceStore(str(_ROOT / "traces.db"))
    run_id = store.new_run(f"fieldagent-eval-{args.target}-{'live' if live else 'dry'}")

    if live:
        est = estimate_cost_usd(cases, model=args.target, window=WINDOW, overlap=OVERLAP)
        print(f"\n=== LIVE RUN cost estimate ===\n"
              f"  ~{est.n_calls} calls · ~{est.input_tokens:,} in + ~{est.output_tokens:,} out tokens\n"
              f"  estimated cost: ${est.usd:.2f}  (cap ${args.max_usd:.2f})\n", file=sys.stderr)
        check_cost_gate(est, args.max_usd)  # refuses over cap (raises)
        inner = _build_live_client(args.target)
        client: ModelClient = RecordingClient(inner)
    else:
        fixtures = _load_fixtures(args.target)
        client = RecordedClient(fixtures, strict=True)

    results = evaluate(
        cases, client, model=args.target, window=WINDOW, overlap=OVERLAP,
        concurrency=concurrency, trace=store, run_id=run_id,
    )

    if live and isinstance(client, RecordingClient):
        _FIXTURES.mkdir(parents=True, exist_ok=True)
        _fixture_path(args.target).write_text(json.dumps(client.fixtures, indent=0))
        print(f"Recorded {len(client.fixtures)} fixtures "
              f"({client.live_calls} live calls) → {_fixture_path(args.target)}", file=sys.stderr)

    _write_results(args.target, results)
    f = results["arms"]["pipeline_full"]
    print("\n=== HEADLINE ===")
    print(f"Detection F1 = {f['f1']:.3f}  (P={f['precision']:.3f} / R={f['recall']:.3f}), "
          f"95% CI {f['ci95']}")
    print(f"Agentic lift = +{results['agentic_lift_f1']:.3f} F1  "
          f"(vs single-shot {results['arms']['single_shot']['f1']:.3f})")
    print(f"Verifier contribution = +{results['verifier_contribution_f1']:.3f} F1")
    print(f"\nWrote {_RESULTS}/metrics.{{json,md}} + per_contract.json")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

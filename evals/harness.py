"""Eval harness core: run the four arms, grade span-IoU, compute lift + CIs.

Kept client-agnostic so it runs identically on FakeClient (tests), RecordingClient
(the one live run), and RecordedClient (zero-cost dry-run). The degraded-run guard
refuses to emit numbers from a run that produced no extractions (the
reasoning-ate-max_tokens / 429 failure mode) — never a fabricated 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.model_client import ModelClient, estimate_tokens, prompt_key
from core.pricing import cost
from core.tracing import TraceStore
from evals.metrics import (
    GoldSpan,
    Prediction,
    bootstrap_f1_ci,
    match_contract,
    prf1,
    span_iou,
)
from fieldagent import baselines, extractor, verifier
from fieldagent.chunker import chunk_text
from fieldagent.clauses import RISK_TYPES
from fieldagent.pipeline import TracingClient, analyze
from fieldagent.types import Candidate, Finding

ARMS = ("keyword", "single_shot", "pipeline_no_verifier", "pipeline_full")
_CANONICAL = "deepseek-chat"


class DegradedRunError(RuntimeError):
    """Raised when a run produced no usable extractions — emitting F1 would be a lie."""


class CostGateError(RuntimeError):
    """Raised when a live run's pre-estimate exceeds FIELDAGENT_MAX_USD."""


def check_cost_gate(est: CostEstimate, max_usd: float) -> None:
    if est.usd > max_usd:
        raise CostGateError(
            f"estimated ${est.usd:.2f} ({est.n_calls} calls) exceeds the ${max_usd:.2f} cap "
            "(FIELDAGENT_MAX_USD). Raise the cap deliberately or shrink the held-out set."
        )


@dataclass
class ContractCase:
    doc_id: str
    text: str
    gold: list[GoldSpan]


@dataclass
class CostEstimate:
    usd: float
    n_calls: int
    input_tokens: int
    output_tokens: int


@dataclass
class ArmResult:
    name: str
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    ci: tuple[float, float]
    per_type: dict[str, dict[str, float]] = field(default_factory=dict)
    per_contract: list[tuple[int, int, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name, "tp": self.tp, "fp": self.fp, "fn": self.fn,
            "precision": round(self.precision, 4), "recall": round(self.recall, 4),
            "f1": round(self.f1, 4), "ci95": [self.ci[0], self.ci[1]],
            "per_type": self.per_type, "per_contract": self.per_contract,
        }


def _preds_from(spans: list[Candidate] | list[Finding]) -> list[Prediction]:
    return [Prediction(s.clause_type, s.start, s.end) for s in spans]


def _grade(name: str, cases: list[ContractCase],
           preds_per_case: list[list[Prediction]], *, threshold: float = 0.5) -> ArmResult:
    per_contract: list[tuple[int, int, int]] = []
    # per-type micro counts
    type_counts: dict[str, list[int]] = {t: [0, 0, 0] for t in RISK_TYPES}
    for case, preds in zip(cases, preds_per_case, strict=True):
        tp, fp, fn = match_contract(preds, case.gold, threshold=threshold)
        per_contract.append((tp, fp, fn))
        # per-type breakdown
        for t in RISK_TYPES:
            p_t = [p for p in preds if p.clause_type == t]
            g_t = [g for g in case.gold if g.clause_type == t]
            ttp, tfp, tfn = match_contract(p_t, g_t, threshold=threshold)
            type_counts[t][0] += ttp
            type_counts[t][1] += tfp
            type_counts[t][2] += tfn
    tp = sum(t for t, _, _ in per_contract)
    fp = sum(f for _, f, _ in per_contract)
    fn = sum(f for _, _, f in per_contract)
    p, r, f1 = prf1(tp=tp, fp=fp, fn=fn)
    ci = bootstrap_f1_ci(per_contract, iters=2000, seed=0)
    per_type: dict[str, dict[str, float]] = {}
    for t, (ttp, tfp, tfn) in type_counts.items():
        if ttp + tfp + tfn == 0:
            continue
        pp, rr, ff = prf1(tp=ttp, fp=tfp, fn=tfn)
        per_type[t] = {"precision": round(pp, 3), "recall": round(rr, 3),
                       "f1": round(ff, 3), "tp": ttp, "fp": tfp, "fn": tfn, "gold": ttp + tfn}
    return ArmResult(name, tp, fp, fn, p, r, f1, ci, per_type, per_contract)


def _detection_recall(cases: list[ContractCase], preds_per_case: list[list[Prediction]]) -> float:
    """Loose recall: fraction of gold clauses for which a prediction of the CORRECT type
    overlaps the gold span at all (IoU>0). Separates 'found the clause' from 'span tight
    enough for IoU>=0.5' — the gap is span-boundary loss, not a true miss."""
    found = total = 0
    for case, preds in zip(cases, preds_per_case, strict=True):
        for g in case.gold:
            total += 1
            if any(p.clause_type == g.clause_type
                   and span_iou((p.start, p.end), (g.start, g.end)) > 0 for p in preds):
                found += 1
    return round(found / total, 4) if total else 0.0


def evaluate(
    cases: list[ContractCase], client: ModelClient, *, model: str,
    window: int = 6000, overlap: int = 800, concurrency: int = 4,
    min_confidence: float = 0.5,
    trace: TraceStore | None = None, run_id: str | None = None,
) -> dict[str, Any]:
    """Run all four arms over the cases, grade, and return a results dict."""
    ss_client: ModelClient = client
    if trace is not None and run_id is not None:
        ss_client = TracingClient(client, trace, run_id, "single_shot")

    preds: dict[str, list[list[Prediction]]] = {a: [] for a in ARMS}
    total_candidates = 0
    for case in cases:
        preds["keyword"].append(_preds_from(baselines.keyword_baseline(case.text)))
        preds["single_shot"].append(
            _preds_from(baselines.single_shot(ss_client, case.text, model=model)))
        nover = analyze(client, case.text, model=model, window=window, overlap=overlap,
                        verify=False, concurrency=concurrency, trace=trace, run_id=run_id)
        full = analyze(client, case.text, model=model, window=window, overlap=overlap,
                       verify=True, concurrency=concurrency, min_confidence=min_confidence,
                       trace=trace, run_id=run_id)
        total_candidates += len(nover)
        preds["pipeline_no_verifier"].append(_preds_from(nover))
        preds["pipeline_full"].append(_preds_from(full))

    if total_candidates == 0:
        raise DegradedRunError(
            f"run produced 0 extractions across {len(cases)} contracts — aborting "
            "(reasoning truncation / rate-limit?). Refusing to emit a fabricated F1."
        )

    arms = {a: _grade(a, cases, preds[a]) for a in ARMS}
    full_f1 = arms["pipeline_full"].f1
    # IoU-threshold sensitivity (headline uses 0.5; this shows robustness)
    sweep = {}
    for thr in (0.1, 0.3, 0.5, 0.7):
        sweep[str(thr)] = {
            "pipeline_full": round(_grade("full", cases, preds["pipeline_full"], threshold=thr).f1, 4),
            "single_shot": round(_grade("ss", cases, preds["single_shot"], threshold=thr).f1, 4),
        }
    return {
        "arms": {a: arms[a].to_dict() for a in ARMS},
        "agentic_lift_f1": round(full_f1 - arms["single_shot"].f1, 4),
        "verifier_contribution_f1": round(full_f1 - arms["pipeline_no_verifier"].f1, 4),
        "detection_recall_full": _detection_recall(cases, preds["pipeline_full"]),
        "span_recall_full": round(arms["pipeline_full"].recall, 4),
        "iou_threshold_sweep": sweep,
        "meta": {
            "contracts_processed": len(cases),
            "total_candidate_extractions": total_candidates,
            "iou_threshold": 0.5,
            "model": model,
            "window": window,
            "overlap": overlap,
        },
    }


def estimate_cost_usd(
    cases: list[ContractCase], *, model: str, window: int = 6000, overlap: int = 800,
) -> CostEstimate:
    """Pre-flight cost estimate (printed before the first paid call, gates the run).

    Extraction + single-shot prompt tokens are known exactly; output and the
    verification pass are estimated conservatively (deepseek-v4-pro bills hidden
    reasoning as output, so output is padded)."""
    in_tok = 0
    out_tok = 0
    n_calls = 0
    OUT_EXTRACT = 1200   # generous: reasoning tokens billed as output
    OUT_VERIFY = 600
    sys_ex = len(extractor._SYSTEM) // 4
    sys_ss = len(baselines._SINGLE_SHOT_SYSTEM) // 4
    sys_vf = len(verifier._SYSTEM) // 4
    for case in cases:
        # single-shot: 1 call over the whole contract
        in_tok += sys_ss + estimate_tokens(case.text[:baselines._SINGLE_SHOT_BUDGET]) + 400
        out_tok += OUT_EXTRACT
        n_calls += 1
        # extraction: one call per chunk
        chunks = chunk_text(case.text, window=window, overlap=overlap)
        for ch in chunks:
            in_tok += sys_ex + estimate_tokens(extractor.build_prompt(ch.text))
            out_tok += OUT_EXTRACT
            n_calls += 1
        # verification allowance: ~2 candidates per chunk
        est_cands = max(1, len(chunks) * 2)
        in_tok += est_cands * (sys_vf + 400)
        out_tok += est_cands * OUT_VERIFY
        n_calls += est_cands
    usd = cost(_CANONICAL, in_tok, out_tok)
    return CostEstimate(usd=usd, n_calls=n_calls, input_tokens=in_tok, output_tokens=out_tok)


class RecordingClient:
    """Wraps a real client: caches by prompt_key (no double-spend across arms) AND
    serializes every response so the run replays for free via RecordedClient."""

    def __init__(self, inner: ModelClient, budget_usd: float = 2.0) -> None:
        self._inner = inner
        self.fixtures: dict[str, dict[str, Any]] = {}
        self.live_calls = 0
        self.spent_usd = 0.0
        self._budget_usd = budget_usd

    def complete(self, *, model: str, system: str,
                 messages: list[dict[str, Any]], max_tokens: int):  # noqa: ANN201
        key = prompt_key(model, system, messages)
        if key in self.fixtures:
            return self._replay(key)
        from core.orchestrator import retry
        from core.types import ModelError, RateLimitError
        resp = retry(
            lambda: self._inner.complete(model=model, system=system, messages=messages,
                                         max_tokens=max_tokens),
            attempts=4, backoff=1.0, exceptions=(RateLimitError, ModelError),
        )
        self.live_calls += 1
        self.spent_usd += resp.cost_usd
        if self.spent_usd > self._budget_usd:
            raise CostGateError(
                f"live spend ${self.spent_usd:.2f} exceeded the ${self._budget_usd:.2f} hard "
                f"ceiling after {self.live_calls} calls — aborting to contain cost."
            )
        self.fixtures[key] = {
            "text": resp.text, "model": resp.model,
            "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens,
            "latency_ms": resp.latency_ms, "stop_reason": resp.stop_reason,
        }
        return resp

    def _replay(self, key: str):  # noqa: ANN202
        from core.types import ModelResponse
        f = self.fixtures[key]
        return ModelResponse(
            text=str(f["text"]), model=str(f["model"]),
            input_tokens=int(f["input_tokens"]), output_tokens=int(f["output_tokens"]),
            cost_usd=cost(str(f["model"]), int(f["input_tokens"]), int(f["output_tokens"])),
            latency_ms=float(f["latency_ms"]), stop_reason=str(f["stop_reason"]),
        )

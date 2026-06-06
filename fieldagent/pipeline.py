"""The agentic pipeline: chunk → extract → verify → dedupe/merge → Findings.

Every model call is traced (inject a ``TracingClient`` wrapping the real client),
so the run is observable end-to-end and the demo/cost numbers read from the same
SQLite store as Quorum. ``verify=False`` yields the ablation arm (chunked
extraction without the skeptic pass) that isolates the verifier's contribution.
"""
from __future__ import annotations

from typing import Any

from core.model_client import ModelClient
from core.orchestrator import fan_out
from core.tracing import TraceStore
from core.types import ModelResponse
from fieldagent.chunker import chunk_text
from fieldagent.clauses import CLAUSES
from fieldagent.extractor import extract_chunk
from fieldagent.metrics_span import iou as _iou  # local re-export to avoid evals import cycle
from fieldagent.types import Candidate, Chunk, Finding
from fieldagent.verifier import verify_candidates


class TracingClient:
    """Wraps a ModelClient; records each ``complete`` as a labeled span. Thread-safe."""

    def __init__(self, inner: ModelClient, store: TraceStore, run_id: str,
                 label: str, parent: str | None = None) -> None:
        self._inner = inner
        self._store = store
        self._run_id = run_id
        self._label = label
        self._parent = parent

    def complete(
        self, *, model: str, system: str,
        messages: list[dict[str, Any]], max_tokens: int,
    ) -> ModelResponse:
        with self._store.span(self._label, run_id=self._run_id, parent=self._parent) as sp:
            resp = self._inner.complete(
                model=model, system=system, messages=messages, max_tokens=max_tokens)
            sp.record_response(resp)
            sp.set(chars_out=len(resp.text))
            return resp


def _dedupe(cands: list[Candidate], *, iou_threshold: float = 0.5) -> list[Candidate]:
    """Merge same-type candidates whose spans overlap (>= IoU threshold), keeping the
    longest quote / highest confidence. Removes duplicates produced by chunk overlap."""
    by_type: dict[str, list[Candidate]] = {}
    for c in cands:
        by_type.setdefault(c.clause_type, []).append(c)
    out: list[Candidate] = []
    for _ctype, group in by_type.items():
        group.sort(key=lambda c: (c.start, -(c.end - c.start)))
        kept: list[Candidate] = []
        for c in group:
            merged = False
            for k in kept:
                if _iou((c.start, c.end), (k.start, k.end)) >= iou_threshold or \
                   (c.start < k.end and k.start < c.end):  # any overlap of same type
                    # keep higher confidence; longer span only breaks a confidence tie
                    if (_conf(c), c.end - c.start) > (_conf(k), k.end - k.start):
                        kept[kept.index(k)] = c
                    merged = True
                    break
            if not merged:
                kept.append(c)
        out.extend(kept)
    out.sort(key=lambda c: c.start)
    return out


def _conf(c: Candidate) -> float:
    return c.confidence


def _to_finding(c: Candidate, *, verified: bool) -> Finding:
    clause = CLAUSES[c.clause_type]
    return Finding(
        clause_type=c.clause_type,
        span_text=c.quote,
        start=c.start,
        end=c.end,
        severity=clause.severity,
        risk_note=clause.risk_note,
        confidence=_conf(c) if verified else 1.0,
        verified=verified,
        rationale=c.rationale,
    )


def analyze(
    client: ModelClient,
    contract_text: str,
    *,
    model: str,
    window: int = 6000,
    overlap: int = 800,
    verify: bool = True,
    concurrency: int = 4,
    min_confidence: float = 0.5,
    trace: TraceStore | None = None,
    run_id: str | None = None,
    extract_max_tokens: int = 6000,
) -> list[Finding]:
    """Run the full agentic pipeline on one contract → structured findings."""
    chunks: list[Chunk] = chunk_text(contract_text, window=window, overlap=overlap)
    if not chunks:
        return []

    extract_client: ModelClient = client
    verify_client: ModelClient = client
    if trace is not None and run_id is not None:
        extract_client = TracingClient(client, trace, run_id, "extract")
        verify_client = TracingClient(client, trace, run_id, "verify")

    def _ex(ch: Chunk) -> list[Candidate]:
        return extract_chunk(extract_client, ch, model=model, max_tokens=extract_max_tokens)

    per_chunk = fan_out(chunks, _ex, max_concurrency=concurrency)
    candidates: list[Candidate] = []
    for lst in per_chunk:
        if lst:
            candidates.extend(lst)

    candidates = _dedupe(candidates)

    if not verify:
        return [_to_finding(c, verified=False) for c in candidates]

    kept = verify_candidates(
        verify_client, candidates, contract_text,
        model=model, concurrency=concurrency, min_confidence=min_confidence)
    kept = _dedupe(kept)
    findings = [_to_finding(c, verified=True) for c in kept]
    findings.sort(key=lambda f: (_severity_rank(f.severity), -f.confidence, f.start))
    return findings


_SEV = {"high": 0, "medium": 1, "low": 2}


def _severity_rank(sev: str) -> int:
    return _SEV.get(sev, 3)


def run_summary(findings: list[Finding]) -> dict[str, Any]:
    return {
        "n_findings": len(findings),
        "by_severity": {
            s: sum(1 for f in findings if f.severity == s) for s in ("high", "medium", "low")
        },
        "by_type": {
            t: sum(1 for f in findings if f.clause_type == t)
            for t in {f.clause_type for f in findings}
        },
    }

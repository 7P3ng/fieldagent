"""Skeptic verification pass — the agentic-lift driver.

For each extracted candidate, an independent call argues whether the span is
*really* an instance of that risk-bearing clause type. Candidates that are
refuted or low-confidence are dropped, cutting false positives (the same
adversarial-verification idea reused across Quorum and Aegis). Malformed verifier
output is treated as a conservative DROP — an unverifiable finding is not kept.
"""
from __future__ import annotations

import logging

from core.model_client import ModelClient
from core.orchestrator import fan_out
from fieldagent.clauses import CLAUSES
from fieldagent.extractor import _parse_json_obj
from fieldagent.types import Candidate

_log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a skeptical senior contract attorney reviewing a junior's flagged clause. "
    "You reject anything that is not clearly an instance of the named risk. Return strict JSON only."
)

_CONTEXT_PAD = 350


def _window(context: str, cand: Candidate) -> str:
    lo = max(0, cand.start - _CONTEXT_PAD)
    hi = min(len(context), cand.end + _CONTEXT_PAD)
    return context[lo:hi]


def build_prompt(cand: Candidate, context: str) -> str:
    clause = CLAUSES[cand.clause_type]
    return (
        f'A reviewer flagged the quoted text as a "{cand.clause_type}" clause.\n\n'
        f"DEFINITION of {cand.clause_type}: {clause.definition}\n\n"
        f'FLAGGED QUOTE: "{cand.quote}"\n\n'
        f'SURROUNDING CONTEXT:\n"""\n{_window(context, cand)}\n"""\n\n'
        "Is the flagged quote genuinely an instance of this clause type (not a mere mention, "
        "definition, cross-reference, or a different clause)? Be strict.\n"
        'Respond JSON ONLY: {"verdict": "keep"|"drop", "confidence": 0.0-1.0, "reason": "one line"}.'
    )


def verify_candidate(
    client: ModelClient, cand: Candidate, context: str, *,
    model: str, min_confidence: float = 0.5, max_tokens: int = 3000,
) -> tuple[bool, float, str]:
    """Return ``(keep, confidence, reason)``. Conservative drop on malformed output."""
    resp = client.complete(
        model=model, system=_SYSTEM,
        messages=[{"role": "user", "content": build_prompt(cand, context)}],
        max_tokens=max_tokens,
    )
    obj = _parse_json_obj(resp.text)
    if not obj:
        return (False, 0.0, "unparseable verifier response")
    verdict = str(obj.get("verdict", "")).strip().lower()
    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(obj.get("reason", ""))[:300]
    keep = verdict == "keep" and confidence >= min_confidence
    return (keep, confidence, reason)


def verify_candidates(
    client: ModelClient, cands: list[Candidate], context: str, *,
    model: str, concurrency: int = 4, min_confidence: float = 0.5,
) -> list[Candidate]:
    """Fan out verification; keep only confirmed candidates (annotated with confidence)."""
    def _v(c: Candidate) -> tuple[Candidate, bool, float, str]:
        keep, conf, reason = verify_candidate(
            client, c, context, model=model, min_confidence=min_confidence)
        return (c, keep, conf, reason)

    results = fan_out(
        cands, _v, max_concurrency=concurrency,
        on_error=lambda c, e: _log.warning("verification failed for %s [%d:%d]: %s",
                                            c.clause_type, c.start, c.end, e),
    )
    kept: list[Candidate] = []
    for r in results:
        if r is None:
            continue  # a failed verification degrades to "drop", run continues
        cand, keep, conf, reason = r
        if keep:
            cand.rationale = reason or cand.rationale
            cand.confidence = conf
            kept.append(cand)
    return kept

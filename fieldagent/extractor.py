"""Focused taxonomy extraction over one chunk, via the ModelClient seam.

One call per chunk asks the model which of the 15 risk clause types appear and to
quote each verbatim. We then *locate* each quote in the chunk text (exact, then
whitespace-tolerant) and shift by the chunk's global offset, so every candidate
references absolute positions in the original contract. Malformed output degrades
to "no candidates" — never a crash, never a fabricated span.

Design note: a single per-chunk call (not per-clause-per-chunk) keeps the one
live deepseek-v4-pro run under the cost gate while preserving the agentic levers
(chunking + downstream verification). See evals/benchmark/SCHEMA.md.
"""
from __future__ import annotations

import json
import re
from typing import Any

from core.model_client import ModelClient
from fieldagent.clauses import RISK_TYPES, extraction_taxonomy_block
from fieldagent.types import Candidate, Chunk

_SYSTEM = (
    "You are a meticulous commercial-contract reviewer. You identify risk-bearing clauses and "
    "quote them verbatim. You never invent text. You return strict JSON only."
)

_RISK_SET = set(RISK_TYPES)


def build_prompt(chunk_text: str) -> str:
    return (
        "Identify every risk-bearing clause in the CONTRACT EXCERPT below that matches one of "
        "these clause types. Quote the exact offending text verbatim from the excerpt.\n\n"
        f"CLAUSE TYPES:\n{extraction_taxonomy_block()}\n\n"
        "Rules:\n"
        "- Only flag text actually present in the excerpt; copy the quote character-for-character.\n"
        "- Quote the COMPLETE clause: the full operative sentence(s) that constitute the risk, from "
        "the start of the sentence to its end — not a short fragment or a few words.\n"
        "- Use the clause-type name EXACTLY as written above.\n"
        "- A clause type may appear zero, one, or several times. Omit types that do not appear.\n"
        '- Respond with JSON ONLY: {"findings": [{"clause_type": "...", "quote": "...", '
        '"why": "one short reason"}]}. If none, return {"findings": []}.\n\n'
        f"CONTRACT EXCERPT:\n\"\"\"\n{chunk_text}\n\"\"\""
    )


def _parse_json_obj(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a model response (tolerates fences/prose)."""
    if not text:
        return None
    # strip ```json ... ``` fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if (start != -1 and end > start) else None
    if candidate is None:
        return None
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def locate_span(haystack: str, needle: str) -> tuple[int, int] | None:
    """Find ``needle`` in ``haystack``: exact first, then whitespace-tolerant.

    Returns ``(start, end)`` char offsets into ``haystack`` or ``None``. The
    whitespace-tolerant pass matches a quote whose internal spacing/newlines
    differ from the source (common with copied contract text).
    """
    needle = needle.strip()
    if not needle:
        return None
    idx = haystack.find(needle)
    if idx != -1:
        return (idx, idx + len(needle))
    # whitespace-flexible: tokens separated by \s+
    tokens = needle.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    m = re.search(pattern, haystack)
    if m:
        return (m.start(), m.end())
    return None


def extract_chunk(
    client: ModelClient, chunk: Chunk, *, model: str, max_tokens: int = 4000
) -> list[Candidate]:
    """Run focused taxonomy extraction on one chunk → located candidates."""
    resp = client.complete(
        model=model, system=_SYSTEM,
        messages=[{"role": "user", "content": build_prompt(chunk.text)}],
        max_tokens=max_tokens,
    )
    obj = _parse_json_obj(resp.text)
    if not obj:
        return []
    findings = obj.get("findings")
    if not isinstance(findings, list):
        return []
    out: list[Candidate] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        ctype = f.get("clause_type")
        quote = f.get("quote")
        if ctype not in _RISK_SET or not isinstance(quote, str) or not quote.strip():
            continue
        loc = locate_span(chunk.text, quote)
        if loc is None:
            continue  # never emit an unlocatable (hallucinated) span
        ls, le = loc
        out.append(Candidate(
            clause_type=ctype,
            quote=chunk.text[ls:le],
            start=chunk.start + ls,
            end=chunk.start + le,
            rationale=str(f.get("why", ""))[:300],
            chunk_index=chunk.index,
        ))
    return out

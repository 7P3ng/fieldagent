"""The two comparison points for the agentic-lift claim.

1. ``keyword_baseline`` — a regex/keyword floor: for each clause type, trigger
   patterns flag the enclosing sentence. Cheap, no model, high recall / low
   precision — the "could a grep do it?" floor.
2. ``single_shot`` — one naive LLM pass over the whole contract (no chunking, no
   verification). The realistic baseline the agentic pipeline must beat.

Both emit ``Candidate`` spans with absolute offsets so the same span-IoU metric
grades them identically to the pipeline.
"""
from __future__ import annotations

import re

from core.model_client import ModelClient
from fieldagent.clauses import RISK_TYPES
from fieldagent.extractor import _parse_json_obj, locate_span
from fieldagent.types import Candidate

# Trigger patterns per clause type (case-insensitive). The floor, not the ceiling.
_PATTERNS: dict[str, list[str]] = {
    "Uncapped Liability": [r"unlimited liability", r"shall not (apply|be subject) to (the|any).{0,20}(cap|limit)",
                           r"no (limit|cap) on (its )?liabilit", r"exclude[ds]? from the (cap|limitation)"],
    "Cap On Liability": [r"in no event shall.{0,60}exceed", r"aggregate liabilit\w+.{0,40}(not exceed|limited to)",
                         r"liabilit\w+.{0,40}(shall (not exceed|be limited)|limited to)", r"maximum.{0,20}liabilit"],
    "Liquidated Damages": [r"liquidated damages", r"as a penalty", r"not as a penalty"],
    "Renewal Term": [r"automatically renew", r"auto-?renew", r"renewal term", r"evergreen",
                     r"renew\w*.{0,20}(successive|additional|further).{0,15}(term|period)"],
    "Non-Compete": [r"non-?compete", r"shall not compete", r"not.{0,20}engage in.{0,25}compet",
                    r"covenant not to compete"],
    "Exclusivity": [r"exclusive (right|basis|license|distributor|supplier|arrangement)",
                    r"sole and exclusive", r"on an exclusive basis", r"exclusively"],
    "No-Solicit Of Employees": [r"not.{0,20}solicit.{0,25}employ", r"no-?solicit", r"not.{0,15}(hire|poach)",
                                r"non-?solicitation"],
    "Most Favored Nation": [r"most favou?red (nation|customer)", r"\bMFN\b", r"no less favou?rable",
                            r"at least as favou?rable"],
    "Ip Ownership Assignment": [r"hereby assign", r"work made for hire", r"shall own all.{0,30}(right|intellectual)",
                                r"ownership of.{0,30}(intellectual property|inventions|work product|deliverable)"],
    "License Grant": [r"hereby grant\w*.{0,40}licen[sc]e", r"grant\w*.{0,25}\ba\b.{0,15}licen[sc]e",
                      r"licen[sc]e to (use|reproduce|distribute|sublicen)"],
    "Termination For Convenience": [r"terminate.{0,40}for (any reason|convenience|no reason)",
                                    r"terminate.{0,30}without cause", r"for convenience"],
    "Anti-Assignment": [r"(not|may not|shall not).{0,20}assign", r"assign\w*.{0,30}prior written consent",
                        r"prior written consent.{0,30}assign"],
    "Change Of Control": [r"change (of|in) control", r"\bmerger\b", r"acquisition",
                          r"sale of (all|substantially all)"],
    "Source Code Escrow": [r"source code escrow", r"escrow.{0,20}source code", r"\bescrow\b"],
    "Audit Rights": [r"right to audit", r"\baudit\b.{0,30}(records|books)", r"inspect.{0,20}(records|books)",
                     r"right to examine.{0,20}(books|records)"],
}

_SENT_SPLIT = re.compile(r"(?<=[.;:\n])\s+")


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Char ranges of rough sentences (split on .;:newline + whitespace)."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for piece in _SENT_SPLIT.split(text):
        if not piece:
            continue
        start = text.find(piece, pos)
        if start == -1:
            start = pos
        end = start + len(piece)
        spans.append((start, end))
        pos = end
    return spans


def keyword_baseline(text: str) -> list[Candidate]:
    """Regex floor: each trigger flags its enclosing sentence as that clause type."""
    sentences = _sentence_spans(text)
    seen: set[tuple[str, int, int]] = set()
    out: list[Candidate] = []
    for ctype in RISK_TYPES:
        for pat in _PATTERNS[ctype]:
            for m in re.finditer(pat, text, re.IGNORECASE):
                # enclosing sentence (fallback: a window around the match)
                span = next(((s, e) for s, e in sentences if s <= m.start() < e), None)
                if span is None:
                    span = (max(0, m.start() - 60), min(len(text), m.end() + 60))
                key = (ctype, span[0], span[1])
                if key in seen:
                    continue
                seen.add(key)
                out.append(Candidate(
                    clause_type=ctype, quote=text[span[0]:span[1]],
                    start=span[0], end=span[1],
                    rationale=f"keyword match: /{pat}/", chunk_index=-1,
                ))
    return out


_SINGLE_SHOT_SYSTEM = (
    "You are a contract reviewer. Read the whole contract and list every risk-bearing clause. "
    "Return strict JSON only."
)
# Naive baseline: cap the whole-contract prompt (no chunking — that's the point).
_SINGLE_SHOT_BUDGET = 28000


def single_shot(
    client: ModelClient, text: str, *, model: str, max_tokens: int = 4000
) -> list[Candidate]:
    """One naive pass over the whole contract — no chunking, no verification."""
    from fieldagent.clauses import extraction_taxonomy_block

    body = text[:_SINGLE_SHOT_BUDGET]
    prompt = (
        "List every risk-bearing clause in this contract matching one of the clause types below. "
        "Quote each verbatim.\n\n"
        f"CLAUSE TYPES:\n{extraction_taxonomy_block()}\n\n"
        '- Use the clause-type name EXACTLY as written. Copy quotes character-for-character.\n'
        '- Respond with JSON ONLY: {"findings": [{"clause_type": "...", "quote": "...", "why": "..."}]}.\n\n'
        f'CONTRACT:\n"""\n{body}\n"""'
    )
    resp = client.complete(
        model=model, system=_SINGLE_SHOT_SYSTEM,
        messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens,
    )
    obj = _parse_json_obj(resp.text)
    if not obj or not isinstance(obj.get("findings"), list):
        return []
    risk_set = set(RISK_TYPES)
    out: list[Candidate] = []
    for f in obj["findings"]:
        if not isinstance(f, dict):
            continue
        ctype = f.get("clause_type")
        quote = f.get("quote")
        if ctype not in risk_set or not isinstance(quote, str) or not quote.strip():
            continue
        loc = locate_span(body, quote)
        if loc is None:
            continue
        ls, le = loc
        out.append(Candidate(
            clause_type=ctype, quote=body[ls:le], start=ls, end=le,
            rationale=str(f.get("why", ""))[:300], chunk_index=-1,
        ))
    return out

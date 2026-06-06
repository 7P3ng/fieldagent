"""Emit the exact harness prompts for a cross-model (Claude) validation subset.

Plan-auth path: subagents (Max 20x, NOT claude -p / Agent-SDK credit) act as the
Claude model. This prints the prompts to fill; responses are recorded to
claude_responses.json and graded by cross_model.py with the same span-IoU metric.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.run_eval import load_heldout
from fieldagent import baselines
from fieldagent.chunker import chunk_text
from fieldagent.clauses import extraction_taxonomy_block
from fieldagent.extractor import _SYSTEM as EX_SYS
from fieldagent.extractor import build_prompt

N = 8
WINDOW, OVERLAP = 9000, 1200  # larger windows → fewer chunks → fewer subagent calls
OUT = Path(__file__).parent / "fixtures" / "claude_prompts.json"


def ss_prompt(text: str) -> tuple[str, str]:
    body = text[: baselines._SINGLE_SHOT_BUDGET]
    prompt = (
        "Identify every risk-bearing clause in the COMPLETE CONTRACT below that matches one of "
        "these clause types. Quote each verbatim.\n\n"
        f"CLAUSE TYPES:\n{extraction_taxonomy_block()}\n\n"
        "Rules:\n- Only flag text actually present; copy the quote character-for-character.\n"
        "- Quote the COMPLETE clause: the full operative sentence(s), not a fragment.\n"
        "- Use the clause-type name EXACTLY as written above.\n"
        "- This is the entire contract. A commercial contract typically contains SEVERAL "
        "(often 5-12) risk-bearing clauses spanning multiple types — be exhaustive.\n"
        '- Respond with JSON ONLY: {"findings": [{"clause_type": "...", "quote": "...", "why": "..."}]}.\n\n'
        f'CONTRACT:\n"""\n{body}\n"""'
    )
    return baselines._SINGLE_SHOT_SYSTEM, prompt


def main() -> int:
    cases = sorted(load_heldout(), key=lambda c: len(c.text))[:N]
    spec: list[dict[str, Any]] = []
    n_calls = 0
    for c in cases:
        sys_ss, p_ss = ss_prompt(c.text)
        chunks = chunk_text(c.text, window=WINDOW, overlap=OVERLAP)
        ex = [{"chunk": ch.index, "system": EX_SYS, "user": build_prompt(ch.text)} for ch in chunks]
        spec.append({"doc_id": c.doc_id, "n_chars": len(c.text),
                     "single_shot": {"system": sys_ss, "user": p_ss},
                     "extract": ex})
        n_calls += 1 + len(ex)
    OUT.write_text(json.dumps(spec, indent=1))
    print(f"{len(cases)} contracts → {n_calls} subagent calls "
          f"({len(cases)} single-shot + {n_calls - len(cases)} extraction)")
    for s in spec:
        print(f"  {s['doc_id'][:34]:36s} {s['n_chars']:6d} chars, {len(s['extract'])} chunks")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

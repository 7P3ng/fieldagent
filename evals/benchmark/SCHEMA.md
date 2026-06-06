# CUAD schema (inspected 2026-06-06) — the grading contract

**Source:** HuggingFace `theatticusproject/cuad` → `CUAD_v1/CUAD_v1.json`
**Pinned sha256:** `ed0b77d85bdf4014d7495800e8e4a70565b48ee6f8a2e5dca9cf8655dbf10eae` (40,128,638 bytes)
**License:** CC BY 4.0 — The Contract Understanding Atticus Dataset (CUAD) v1, The Atticus Project.

## Shape (SQuAD-style, verified by inspection)

```
{ "version": "aok_v1.0",
  "data": [                         # 510 documents
    { "title": "<DOC_ID>",
      "paragraphs": [               # always exactly 1
        { "context": "<full raw contract text>",
          "qas": [                  # 41 entries — one per CUAD clause category
            { "id": "<DOC_ID>__<Category>",
              "question": "Highlight the parts ... related to \"<Category>\" ...",
              "is_impossible": false,
              "answers": [ { "text": "<verbatim span>", "answer_start": <char offset into context> } ] }
          ] } ] } ] }
```

- A gold span = `[answer_start, answer_start + len(text))` (half-open char interval into `context`).
- A category with `is_impossible: true` / empty `answers` is **absent** from that contract (a true negative for that type).
- The clause-type label is the **exact** string after `__` in `id` (e.g. `Cap On Liability`, `Renewal Term`,
  `Ip Ownership Assignment`, `Source Code Escrow`). Matching is **case- and string-exact** — the FieldAgent
  taxonomy keys (`fieldagent/clauses.py`) are these exact strings, or gold matching silently fails.

## The 15 risk-bearing types FieldAgent targets (subset of CUAD's 41)
Uncapped Liability · Cap On Liability · Liquidated Damages · Renewal Term · Non-Compete · Exclusivity ·
No-Solicit Of Employees · Most Favored Nation · Ip Ownership Assignment · License Grant ·
Termination For Convenience · Anti-Assignment · Change Of Control · Source Code Escrow · Audit Rights

## Grading metric (built against THIS shape)
A predicted finding `(clause_type, start, end)` matches a gold span iff **clause_type is identical** AND
**char-interval IoU ≥ 0.5** (`evals/metrics.py:span_iou`). Per contract: greedy 1-gold↔1-pred matching;
TP = matched, FP = unmatched preds, FN = unmatched gold. Aggregated micro across the held-out set, with
per-type breakdown and a percentile bootstrap 95% CI over contracts. **No LLM judge in the success path.**

## Data hygiene (public repo)
Raw CUAD text is **never committed** (`evals/benchmark/raw/` is gitignored; real commercial contracts/PII).
Only `heldout_gold.json` — clause_type + char offsets + an 8-char text hash (integrity check, not the text) —
is committed for the 20 held-out contracts. `fetch_cuad.py` reconstitutes raw text locally at eval time;
offsets are stable because the dataset is sha256-pinned.

## Extractor design note (cost-driven, faithful to the agentic claim)
deepseek-v4-pro bills hidden reasoning tokens as output. Per-clause-per-chunk fan-out (chunks × 15) on the
20-contract held-out set would exceed the $1 cost gate. The extractor therefore issues **one focused
taxonomy-extraction call per chunk** (all 15 clause types in a single prompt), fanned out per chunk via the
orchestrator. The agentic levers vs. naive single-shot are preserved and individually ablated: **chunking**
(single-shot vs. chunked-no-verifier) and **verification** (chunked-no-verifier vs. full pipeline).

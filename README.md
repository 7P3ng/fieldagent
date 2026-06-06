# FieldAgent — Contract Red-Flag Finder

> Portfolio artifact #3 (sibling to [Quorum](https://github.com/7P3ng/quorum) agent infra and [Aegis](https://github.com/7P3ng/aegis) agent-safety).
> Drop an agent into a messy real-world vertical — commercial-contract review — and **measure** that
> the agentic design beats naive single-shot, graded against a public gold dataset (CUAD).

**Live demo:** https://fieldagent.thomaspeng.ca  ·  **Dataset:** [CUAD v1](https://www.atticusprojectai.org/cuad) (CC BY 4.0)

## Headline numbers
_(`make eval-dry` reproduces these offline from committed fixtures, zero cost — a test asserts it)_

| Claim | Result |
|---|---|
| **Detection** | **F1 = 0.548** (P = 0.74 / R = 0.44), 95% CI [0.46, 0.64] — 20 held-out CUAD contracts, 15 risk clause types, 191 gold spans, span-IoU ≥ 0.5. **Detection recall 0.59** (right clause type, any overlap): most of the recall gap is clauses found but quoted too tightly to clear IoU 0.5, not true misses. |
| **Agentic lift** | full pipeline = **+0.21 F1 over a keyword/regex floor** (0.337 → 0.548) — the clean, baseline-independent comparison. The skeptic verifier shifts precision 0.72 → 0.74 but its F1 effect (−0.014) is **not distinguishable from zero** at n=20 (overlapping CIs). _Caveat on the single-shot LLM baseline: it scores far lower (0.10 F1), but that number is **output-budget-confounded** — deepseek-v4-pro's reasoning truncates the one-pass response on 17/20 contracts (the committed fixtures use a 4k-token cap); an 8k-token spot-check recovered 5–7 clauses/contract. The single-shot gap is therefore an **upper bound**; a full fair-baseline re-run is pending DeepSeek credit (`make eval-live`). See [writeup §4](docs/writeup.md)._ |

![demo](docs/assets/demo.gif)

## What it does
Reads a real contract and flags **risk-bearing clauses** — exact offending span, a severity, and a
plain-English "why this is risky" — for 15 CUAD clause types (Uncapped Liability, Cap On Liability,
Liquidated Damages, Renewal Term, Non-Compete, Exclusivity, No-Solicit Of Employees, Most Favored Nation,
IP Ownership Assignment, License Grant, Termination For Convenience, Anti-Assignment, Change Of Control,
Source Code Escrow, Audit Rights).

## Architecture
`chunk → focused taxonomy extraction (fan-out) → skeptic verification → dedupe/merge → structured findings`,
fully traced. Vendors Quorum's kernel (`core/`): the `ModelClient` seam (Fake/Recorded/DeepSeek/Anthropic),
SQLite tracing, the concurrent orchestrator, and per-model pricing. Grading is **span-IoU** (no LLM judge in
the success path). See [`docs/writeup.md`](docs/writeup.md) for the full methodology + ablations + threats.

![architecture](docs/architecture.svg)

## Run it
```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
make test          # unit suite, no network, no paid calls
make fetch-cuad    # sha256-pinned CUAD_v1.json (raw text stays local, gitignored)
make eval-dry      # reproduce the headline tables from committed fixtures (zero cost)
# Live (needs a DeepSeek key + opt-in; prints a cost estimate and refuses runs over $1):
export OSSLLM_API_KEY=...   # or source your DeepSeek env file
FIELDAGENT_LIVE=1 make eval-live
# Analyze your own contract:
FIELDAGENT_LIVE=1 .venv/bin/python cli/analyze.py path/to/contract.txt
```

## Attribution
This project evaluates against **CUAD v1** — The Contract Understanding Atticus Dataset, The Atticus Project,
https://www.atticusprojectai.org/cuad — licensed CC BY 4.0. Raw contract text is not redistributed here;
`evals/benchmark/fetch_cuad.py` reconstitutes it locally (sha256-pinned).

# FieldAgent — a contract red-flag finder, measured

> Mini research note. Two claims, the methodology behind them, the ablations that
> isolate *why* the agentic design wins, and an honest threats-to-validity section.
> Numbers are produced by `evals/run_eval.py` and reproduced offline by `make eval-dry`.
> Placeholders `⟦…⟧` are filled from the committed `evals/results/metrics.json`.

## 1. The task

Commercial contracts hide risk in their clauses: an uncapped-liability carve-out, an
auto-renewal you must cancel in a 30-day window, an exclusivity grant that forecloses every
other partner. FieldAgent reads a contract and emits, for each of **15 risk-bearing clause
types**, the **exact offending span**, a **severity**, and a **plain-English risk note** — the
output a deal reviewer actually wants.

Ground truth is **CUAD** (the Contract Understanding Atticus Dataset, CC BY 4.0): ~510
commercial contracts, expert-labeled spans for 41 clause categories. We target the 15
risk-bearing categories and evaluate on a **20-contract held-out subset** (191 gold spans).

## 2. Metric — span-IoU, no judge model

A predicted finding `(clause_type, start, end)` **matches** a gold span iff the clause type
is identical **and** the half-open char-interval **IoU ≥ 0.5** (the CUAD-standard threshold).
Per contract we do greedy 1-gold↔1-pred matching; TP = matched, FP = unmatched predictions,
FN = unmatched gold. We aggregate **micro** across contracts and report **precision / recall /
F1**, a **per-clause-type** breakdown, and a **percentile bootstrap 95% CI** resampling
contracts (`evals/metrics.py`). Crucially, **no LLM judges the success path** — grading is a
pure function, so the numbers cannot drift with a grader model's mood, and dry-run and live
runs grade identically.

## 3. System

`chunk → focused taxonomy extraction → skeptic verification → dedupe/merge → findings`,
every model call traced to SQLite. It vendors **Quorum's kernel** (`core/`): the `ModelClient`
seam (Fake/Recorded/DeepSeek/Anthropic), the concurrent orchestrator (fan-out + retry/backoff
+ graceful degradation), per-model pricing, and bootstrap CIs — the through-line across the
Quorum / Aegis / FieldAgent trio is **adversarial verification**.

- **Chunker** — overlapping char windows carrying global offsets, so a clause that straddles a
  boundary is wholly present in at least one window and every extracted span maps back to an
  absolute position in the document.
- **Extractor** — one **focused taxonomy-extraction call per chunk** (all 15 clause definitions
  in the prompt), fanned out via the orchestrator; quotes are located back to global offsets
  (exact, then whitespace-tolerant), and a hallucinated quote that isn't in the text is dropped
  rather than emitted.
- **Verifier** — an independent **skeptic** call per candidate argues whether the span is really
  an instance of that clause type; refuted or low-confidence candidates are dropped. This is the
  false-positive cutter.
- **Baselines** — a **keyword/regex floor** (could a grep do it?) and a **naive single-shot LLM**
  (whole contract, one pass, no chunking, no verification) — the comparators for the lift claim.

### Why one call per chunk (and not per-clause-per-chunk)
The spec's instinct is per-clause focused extraction. On the 20-contract held-out set with
deepseek-v4-pro — whose hidden reasoning is **billed as output tokens** — `chunks × 15` calls
would exceed the project's $1 cost gate. A single focused call per chunk preserves the two
agentic levers that actually beat single-shot — **chunking** (no long-context recall loss) and
**verification** (FP cut) — and lets us isolate each in the ablation. The live run cost **≈$0.5** (estimate $0.34, 224 calls).

## 4. Results

_(from `evals/results/metrics.md`; reproduce with `make eval-dry`)_

| Arm | P | R | F1 | 95% CI |
|---|---|---|---|---|
| Keyword / regex floor | 0.490 | 0.257 | 0.337 | [0.275, 0.392] |
| Single-shot LLM (baseline) | 0.700 | 0.073 | 0.133 | [0.018, 0.282] |
| Pipeline − verifier (chunked) | 0.721 | 0.461 | 0.562 | [0.473, 0.654] |
| **Pipeline (full, agentic)** | 0.741 | 0.435 | **0.548** | [0.460, 0.637] |

**Claim 1 — detection:** F1 = **0.548** (P 0.741 / R 0.435) on held-out CUAD.
**Claim 2 — agentic lift:** full − single-shot = **+0.415 F1** (0.133 → 0.548). The chunked
no-verifier arm is 0.562 and the full pipeline 0.548 — see the ablation.

### Ablation reading
- **Chunking dominates the lift.** (pipeline−verifier) − single-shot = **+0.429 F1**. The
  single-shot model, asked to read a whole 15–28 K-char contract in one pass, *under-extracts*
  badly: it claimed only **21 findings across 20 contracts** (avg 1.1/contract; 20 of 21 located
  cleanly, so this is genuine recall collapse, not a parsing artifact). Windowing into focused
  chunks recovers **122 candidate spans → 88 true positives** — the recall jumps 0.073 → 0.461.
- **Verification is precision-positive, F1-neutral.** full − (pipeline−verifier) = **−0.014 F1**:
  the skeptic pass dropped 5 false positives *and* 5 true positives, nudging precision 0.721 →
  0.741 while shaving recall 0.461 → 0.435. Reported as measured — *not* threshold-tuned on the
  held-out set to manufacture a positive number. For a red-flag tool, fewer false alarms at equal
  F1 is a favorable trade.
- **IoU sensitivity:** the lift holds across IoU ∈ {0.1, 0.3, 0.5, 0.7} — full pipeline F1
  {0.654, 0.640, 0.548, 0.462} vs single-shot {0.171, 0.161, 0.133, 0.085} — so it is not an
  artifact of the 0.5 threshold.

## 5. Threats to validity

- **Single domain / dataset.** CUAD is one (well-constructed) corpus of mostly US commercial
  contracts; F1 here need not transfer to other jurisdictions, languages, or contract families.
  This is a depth-not-breadth artifact by design.
- **Held-out size.** 20 contracts / 191 gold spans — bounded by the single-live-run cost gate.
  CIs quantify the resulting uncertainty; they are not narrow. Coverage of rare types
  (Source Code Escrow, MFN) is thin and their per-type F1 is noisy.
- **Span granularity.** CUAD gold spans are whole clauses (median ~250 chars); an extractor that
  quotes a correct-but-short fragment is penalized at IoU 0.5. We prompt for complete clauses and
  report the threshold sweep so the reader can see the granularity effect.
- **One model.** Numbers are deepseek-v4-pro. Cross-model (Claude/GPT) is gated on a key and not
  run here; the harness populates a cross-model table when `ANTHROPIC_API_KEY` is present.
- **Verifier shares a family with the extractor.** Skeptic and extractor are the same model in
  different roles; some correlated blind spots survive. A cross-model verifier is future work.

## 6. Reproduce

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
python evals/benchmark/fetch_cuad.py     # sha256-pinned CUAD (raw text gitignored)
make eval-dry                            # replays committed fixtures, zero cost → results/
make test                                # unit suite incl. offline F1 reproduction
```
The live run (one DeepSeek pass, cost-gated) is `FIELDAGENT_LIVE=1 make eval-live`.

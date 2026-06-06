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
| Single-shot LLM (steelmanned, 8k-token budget) | 0.664 | 0.372 | 0.476 | [0.400, 0.549] |
| Pipeline − verifier (chunked) | 0.721 | 0.461 | 0.562 | [0.473, 0.654] |
| **Pipeline (full, agentic)** | 0.741 | 0.435 | **0.548** | [0.460, 0.637] |

**Claim 1 — detection:** F1 = **0.548** (P 0.741 / R 0.435) on held-out CUAD. **Detection recall
is 0.592** (a prediction of the correct type overlaps the gold span at all): of the 56% of gold
not counted at IoU 0.5, ~16 pts are clauses *found in the right place but quoted too tightly* to
clear the span threshold, and ~41% are true misses.
**Claim 2 — agentic lift (the honest version):** once the single-shot baseline gets an adequate
output budget, the lift is **small and within noise — +0.07 F1** (full 0.548 vs fair single-shot 0.476;
95% CIs [0.460, 0.637] and [0.400, 0.549] overlap). The baseline-independent claim is **+0.211 F1 over
a keyword/regex floor** (0.337 → 0.548). An earlier run reported "+0.45 vs single-shot" — a truncation
artifact, dissected in the ablation and section 5.

### Ablation reading
- **The "+0.45 lift" was a single-shot truncation artifact — now resolved.** The first single-shot
  run capped output at 4 000 tokens; deepseek-v4-pro's hidden reasoning ate that budget and **17/20
  responses truncated** (`stop_reason=length`) into unparseable JSON → 0.098 F1. Re-running single-shot
  at **8 000 tokens** (107 findings across 20 contracts, vs ~13 before; 18/20 now finish, 2 large
  contracts still truncate) lifts the fair single-shot to **F1 0.476** — and the agentic lift collapses
  from +0.45 to **+0.07**, the two arms' CIs overlapping ([0.460, 0.637] vs [0.400, 0.549]). The
  apparent lift was almost entirely the baseline being output-truncated, not chunked extraction being
  better. (Committed fixtures are the 8 K run; `make eval-dry` reproduces 0.476 / 0.548.)
- **What chunking actually buys: robustness to output limits.** Per-window extraction recovers 122
  candidate spans → 88 TP regardless of a per-response token ceiling, whereas a single pass over a long
  contract is hostage to its output budget. A real engineering property — just not the "+0.45 detection
  lift" it first looked like.
- **Verification: no F1 effect distinguishable from noise.** full − (pipeline−verifier) =
  **−0.014 F1**. The skeptic pass dropped 5 false positives *and* 5 true positives, shifting
  precision 0.721 → 0.741 and recall 0.461 → 0.435 — but the two arms' 95% CIs overlap almost
  entirely ([0.460, 0.637] vs [0.473, 0.654]), so at n=20 the verifier's contribution is **not
  statistically distinguishable from zero**. Reported as measured — *not* threshold-tuned on the
  held-out set. The adversarial-verification *idea* is the design through-line across Quorum/Aegis/
  FieldAgent; on this high-precision CUAD extractor there is little false-positive headroom for it
  to recover, and we say so rather than overclaim it.
- **IoU sensitivity:** full-pipeline F1 across IoU ∈ {0.1, 0.3, 0.5, 0.7} = {0.654, 0.640, 0.548,
  0.462}; the +0.21 lift over the keyword floor (which barely moves with IoU) holds throughout, so
  the result is not an artifact of the 0.5 threshold.

## 5. Cross-model validation — the lift is model-specific

The headline "+0.45 agentic lift" looked great — and the eval caught it as an artifact, two ways.

**(1) Fix the output budget on DeepSeek.** deepseek-v4-pro's single-shot response truncated (17/20 hit
a 4 K-token cap; reasoning ate the budget before the JSON), collapsing the baseline to 0.098 F1. Re-run
the *same* single-shot at 8 K tokens and it scores **0.476** — the lift falls from +0.45 to **+0.07**
(CIs overlap). The gap was the baseline being truncated, not chunking winning.

**(2) Confirm on a second model.** I re-ran the two arms on **Claude Sonnet** (8 smallest held-out
contracts, 63 gold spans), single-shot elicited *first and standalone*, identical span-IoU grading.
(Plan-auth via in-session subagents — not a paid API call, not the Agent-SDK credit path;
`evals/cross_model.py` grades, `evals/results/cross_model_claude.json` holds the numbers.)

| Model · arm | Single-shot F1 | Chunked (no-verifier) F1 | Chunking lift |
|---|---|---|---|
| DeepSeek-v4-pro — single-shot @4k (truncated) | 0.098 | 0.562 | +0.46 *(artifact)* |
| **DeepSeek-v4-pro — single-shot @8k (fair)** | **0.476**, CI [0.400, 0.549] | 0.562 | **+0.086** |
| **Claude Sonnet (8-contract subset)** | **0.567**, CI [0.514, 0.636] | 0.555, CI [0.509, 0.615] | **−0.012** |

**The lift does not survive on either model once the baseline is not output-truncated** — +0.07–0.09 on
DeepSeek (CIs overlap) and −0.01 on Claude. Chunking's real value is **robustness to a model's
output-budget limits**, not raw detection superiority: given an adequate budget, a single pass matches
the chunked pipeline. A single-model, single-budget eval would have shipped "+0.45" as a headline —
which is exactly why cross-model + budget-sensitivity checks belong in the harness. The claims that
survive: detection F1 0.548 / recall 0.59, and the pipeline beating the keyword floor by +0.21 F1.

## 6. Threats to validity

- **Single domain / dataset.** CUAD is one (well-constructed) corpus of mostly US commercial
  contracts; F1 here need not transfer to other jurisdictions, languages, or contract families.
  This is a depth-not-breadth artifact by design.
- **Held-out size.** 20 contracts / 191 gold spans — bounded by the single-live-run cost gate.
  CIs quantify the resulting uncertainty; they are not narrow. Coverage of rare types
  (Source Code Escrow, MFN) is thin and their per-type F1 is noisy.
- **Span granularity.** CUAD gold spans are whole clauses (median ~250 chars); an extractor that
  quotes a correct-but-short fragment is penalized at IoU 0.5. We prompt for complete clauses and
  report the threshold sweep so the reader can see the granularity effect.
- **Recall on the highest-value types is weak.** Span-IoU recall on Cap On Liability (0.22) and
  IP Ownership Assignment (0.26) — two of the most deal-critical types and the largest gold buckets
  — is low; detection recall (any-overlap) is higher but these types still drive most of the misses.
  A reviewer should treat FieldAgent as high-precision triage, not exhaustive coverage.
- **Verifier effect is within noise.** The −0.014 F1 and the 0.72→0.74 precision shift are not
  separable from sampling noise at n=20 (overlapping CIs). The verifier is retained as the shared
  design pattern, not because it is shown to help here.
- **The agentic lift is small and budget-sensitive** (the section-5 finding). At an adequate output
  budget the DeepSeek lift is +0.07 (CIs overlap) and the Claude lift −0.01; the large "+0.45" only
  appears when the single-shot baseline is output-truncated. 2/20 DeepSeek single-shot responses still
  truncate even at 8 K, so the fair single-shot (0.476) is a slight floor and the true lift is, if
  anything, smaller. The robust claims (detection F1/recall, +0.21 over the keyword floor) do not
  depend on it.
- **Cross-model run is a small subset.** The Claude validation is 8 contracts / 63 gold spans, single
  model, elicited via subagents; treat it as directional (the lift vanishes) rather than a precise
  Claude F1. A full Claude harness run is future work (needs an in-process Claude client).
- **One model.** Numbers are deepseek-v4-pro. Cross-model (Claude/GPT) is gated on a key and not
  run here; the harness populates a cross-model table when `ANTHROPIC_API_KEY` is present.
- **Verifier shares a family with the extractor.** Skeptic and extractor are the same model in
  different roles; some correlated blind spots survive. A cross-model verifier is future work.

## 7. Reproduce

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
python evals/benchmark/fetch_cuad.py     # sha256-pinned CUAD (raw text gitignored)
make eval-dry                            # replays committed fixtures, zero cost → results/
make test                                # unit suite incl. offline F1 reproduction
```
The live run (one DeepSeek pass, cost-gated) is `FIELDAGENT_LIVE=1 make eval-live`.

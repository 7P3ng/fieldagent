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
| Single-shot LLM (steelmanned baseline) | 0.769 | 0.052 | 0.098 | [0.000, 0.213] |
| Pipeline − verifier (chunked) | 0.721 | 0.461 | 0.562 | [0.473, 0.654] |
| **Pipeline (full, agentic)** | 0.741 | 0.435 | **0.548** | [0.460, 0.637] |

**Claim 1 — detection:** F1 = **0.548** (P 0.741 / R 0.435) on held-out CUAD. **Detection recall
is 0.592** (a prediction of the correct type overlaps the gold span at all): of the 56% of gold
not counted at IoU 0.5, ~16 pts are clauses *found in the right place but quoted too tightly* to
clear the span threshold, and ~41% are true misses.
**Claim 2 — agentic lift:** the clean, baseline-independent claim is **+0.211 F1 over a
keyword/regex floor** (0.337 → 0.548). A naive single-shot LLM scores far lower (0.098 F1), but
that number is *output-budget-confounded* (see the ablation) — treat the single-shot gap as an
upper bound, not a headline.

### Ablation reading
- **The single-shot baseline is output-budget-confounded — disclosed, not hidden.** The committed
  single-shot fixtures cap the response at 4 000 tokens, and deepseek-v4-pro's hidden reasoning eats
  that budget: **17/20 single-shot responses truncate** (`stop_reason=length`) into unparseable JSON
  → near-zero findings (0.052 recall, 0.098 F1). This is the brief's own documented gotcha, so the
  headline "+0.45 vs single-shot" **overstates** the gap. A fair re-run at 8 000 tokens was started;
  the two contracts that completed before the shared DeepSeek account hit *Insufficient Balance*
  returned **5 and 7 complete findings** (vs 0 truncated) — a fair single-shot would score materially
  higher and the true lift is smaller (~+0.2–0.3, unquantified pending credit). The clean,
  truncation-free comparison is the **+0.211 F1 over the keyword floor**; `make eval-live` re-records
  the fair single-shot baseline once credit is restored.
- **Chunking still helps, baseline-independently.** Per-window focused extraction recovers **122
  candidate spans → 88 TP** (recall 0.461) where a single 4 K-budget pass collapses. The magnitude of
  the *single-shot* gap is confounded; the direction (chunking > one naive pass) and the floor
  comparison are not.
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
  the result is not an artifact of the 0.5 threshold. (Single-shot numbers inherit the truncation
  confound above.)

## 5. Cross-model validation — the lift is model-specific

The single-model result above has a trap, and the eval caught it. The DeepSeek "+0.45 over
single-shot" is real arithmetic, but it measures the wrong thing: deepseek-v4-pro's single-shot
response **truncates** (17/20 hit the 4 K output cap, reasoning eats the budget before the JSON),
so the baseline collapses to ~0 findings for a reason that has nothing to do with chunking.

To separate "chunking helps" from "the DeepSeek baseline is broken," I re-ran the two arms on a
second model — **Claude Sonnet** — over the 8 smallest held-out contracts (63 gold spans), elicited
single-shot *first and standalone* so it is not primed by chunk focus, and graded with the identical
span-IoU metric. (Plan-auth via in-session subagents — not a paid API call, not the Agent-SDK credit
path; `evals/cross_model.py` grades, `evals/results/cross_model_claude.json` holds the numbers.)

| Model | Single-shot F1 | Chunked (no-verifier) F1 | Chunking lift |
|---|---|---|---|
| DeepSeek-v4-pro | 0.098 *(single-shot truncates 17/20)* | 0.562 | **+0.46** |
| Claude Sonnet (8-contract subset) | **0.567** (P 0.60 / R 0.54), CI [0.514, 0.636] | 0.555, CI [0.509, 0.615] | **−0.012** |

**The lift does not replicate.** Claude finishes its one-pass response (57 findings located, recall
0.54) and single-shot *ties* the chunked pipeline — the two CIs overlap almost completely. So the
DeepSeek lift is an **output-budget artifact**, not evidence that chunked focused extraction beats a
single pass. Chunking's real value is **robustness to a model's output-budget limits**, not raw
detection superiority; on a model without that limit there is nothing to recover.

This is the whole reason cross-model evaluation belongs in the harness: a single-model run would have
shipped "+0.45 agentic lift" as the headline. The honest, baseline-independent claims survive — the
pipeline beats the keyword floor by +0.21 F1, and detection F1/recall stand on their own.

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
- **Single-shot baseline is output-budget-limited on DeepSeek** (the §5 finding). The committed
  single-shot fixtures truncate at 4 000 tokens, so the DeepSeek single-shot F1 is a floor and the
  "+0.45 vs single-shot" an artifact — superseded by the cross-model result, which shows no lift on
  Claude. The robust claims (pipeline F1, detection recall, +0.21 over the keyword floor) do not
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

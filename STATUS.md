# FieldAgent build status — COMPLETE

All phases 0–6 done. Live demo: https://fieldagent.thomaspeng.ca

## Results (one live deepseek-v4-pro run, 224 calls, ~$0.5, under the $1 gate)
- **Detection F1 = 0.548** (P=0.741 / R=0.435), 95% CI [0.460, 0.637]
- **Agentic lift = +0.415 F1** vs single-shot (0.133) — chunking is the dominant driver.
- Verifier: precision 0.721→0.741, F1 −0.014 (precision-positive, F1-neutral — reported honestly).
- Reproduced offline by `make eval-dry` (zero cost); a test asserts it.

## Phases
- [x] Phase 0 — scaffold, vendored kernel, CUAD acquisition + held-out gold (20 contracts/191 spans)
- [x] Phase 1 — span-IoU metric + chunker + 15-clause taxonomy (TDD)
- [x] Phase 2 — extractor + keyword/single-shot baselines (TDD)
- [x] Phase 3 — verifier + traced pipeline (TDD)
- [x] Phase 4 — eval harness + ONE live DeepSeek run (cost-gated, fixtures committed)
- [x] Phase 5 — static web demo + Caddy deploy (live, .git/.env → 404 verified)
- [x] Phase 6 — writeup + README + architecture diagram + CI + code-review fixes

## Verification gates passed
- Independent Sonnet subagent: dry-run reproduces F1/lift exactly; numbers consistent across
  README / writeup / metrics.json / data.json; zero paid calls.
- Code review (Sonnet): integrity-clean (degraded guard, span-IoU, offset math, cost gate);
  3 bugs found + fixed (dedupe priority, verifier observability, fenced-JSON regex).
- Secret scan: no keys/tokens, no .env, no raw CUAD committed; /etc paths only in DEPLOY.md.
- 47 tests green, ruff + mypy clean.

## Notes
- Extractor = one focused taxonomy call per chunk (not per-clause-per-chunk) to keep the single
  live run under the $1 gate (v4-pro bills hidden reasoning). Agentic levers (chunking +
  verification) preserved + individually ablated. See evals/benchmark/SCHEMA.md.
- Visual verification via chrome-headless-shell (full chromium + Playwright MCP were wedged/locked
  by a sibling job on this box); rendered SSG HTML + screenshots confirm the demo.
- Phase 7 (cross-model Claude/GPT) intentionally NOT built — gated on ANTHROPIC_API_KEY.

## Post-review hardening (objective critique pass)
An adversarial review flagged the single-shot baseline as a possible strawman. Addressed:
- **Fair/steelmanned baseline:** single-shot now uses the IDENTICAL system prompt to the extractor
  + an explicit "be exhaustive (5-12 clauses), full contract" instruction + no truncation (held-out
  is size-bounded; cap never fires). It found *fewer* clauses (0.7 vs 1.1/contract), so the lift is
  genuine long-context under-extraction, not a prompt handicap. Agentic lift **+0.415 → +0.450 F1**.
- **Detection-recall metric:** strict span-IoU recall 0.435 vs detection recall (right type, any
  overlap) **0.592** — 16 pts of the gap is tight-quote span loss, not true misses. Surfaced in
  README + writeup + metrics.md.
- **Verifier honesty:** reframed as not-distinguishable-from-noise (overlapping CIs at n=20), not
  "precision-positive" spin.
- **Demo:** now visualizes MISSED gold clauses (dashed, false negatives) + per-contract recall +
  a legend — so the demo shows recall, not just precision.
- Cost: +$0.11 (single-shot-only re-run, 20 calls) on top of the ~$0.5 first run.

## Honesty correction + KNOWN BLOCKER (DeepSeek balance)
**Finding:** the single-shot baseline is *output-budget-confounded*. Its committed fixtures cap the
response at 4 000 tokens, and deepseek-v4-pro's hidden reasoning truncates 17/20 responses
(`stop_reason=length`) → near-zero findings → an inflated "+0.45 vs single-shot" lift. An 8 000-token
spot-check returned 5 and 7 complete findings on the 2 contracts that ran before the shared DeepSeek
account hit **402 Insufficient Balance**.

**Action taken (honest, no fabrication):**
- Re-anchored the headline lift on the **truncation-free keyword floor: +0.211 F1** (0.337→0.548),
  in README, writeup, and the demo. The single-shot comparison is disclosed as an *upper bound*.
- `single_shot` default max_tokens raised 4 000 → 8 000 (fair going forward); committed fixtures
  remain the 4 000 run (dry-run still reproduces), clearly labelled as budget-limited.
- Pipeline F1 (0.548), detection recall (0.592), and the keyword-floor lift do NOT depend on the
  single-shot baseline and stand.

**needs operator:** top up the shared DeepSeek credit, then `FIELDAGENT_LIVE=1 make eval-live`
re-records the fair single-shot baseline at 8 000 tokens and regenerates the honest lift number.

## Cross-model validation (Claude, plan auth) — REPOSITIONED
Ran the lift comparison on a second model (Claude Sonnet, 8 contracts) via in-session subagents on
the Max-20x plan (no claude -p, no paid API). **Finding: the agentic chunking lift is model-specific.**
Claude single-shot F1 0.567 ties Claude chunked 0.555 (lift −0.01, CIs overlap) — the DeepSeek "+0.45"
was an artifact of DeepSeek single-shot truncating. Repositioned README + writeup (§5) + demo to LEAD
with this honest cross-model finding. Robust claims unchanged: detection F1 0.548, recall 0.59,
+0.21 over keyword floor. DeepSeek single-shot fair re-run still pending credit, but now superseded by
the cross-model result.

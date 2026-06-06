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

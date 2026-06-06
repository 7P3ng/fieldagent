# FieldAgent build status

**Last update:** Phase 0 complete.

## Progress
- [x] Phase 0 — scaffold, vendored Quorum kernel (deepseek_client patched for OSSLLM_URL), config,
      fetch_cuad.py (sha256-pinned), CUAD schema inspected (SCHEMA.md), 20 held-out contracts /
      191 gold spans (offsets-only, no raw text), README skeleton.
- [ ] Phase 1 — taxonomy + chunker + span-IoU metric + grading (TDD)
- [ ] Phase 2 — extractor + baselines (TDD)
- [ ] Phase 3 — verifier + pipeline (TDD, traced)
- [ ] Phase 4 — eval harness + ONE live DeepSeek run (cost-gated)
- [ ] Phase 5 — static web demo + deploy
- [ ] Phase 6 — writeup + README + CI

## Key decisions / notes
- **Extractor = one focused taxonomy-extraction call per chunk** (all 15 types), fanned out per chunk —
  not per-clause-per-chunk — to keep the single live deepseek-v4-pro run under the $1 cost gate (v4-pro
  bills hidden reasoning tokens). Agentic levers (chunking, verification) preserved + individually ablated.
  See evals/benchmark/SCHEMA.md.
- **Sibling Aegis build was running** at Phase 0 (shared DeepSeek key). Live run will prefer off-peak;
  degraded-run guard + 429 backoff is the real protection.
- No blockers. CUAD reachable; DeepSeek key readable; deploy DNS already resolves.

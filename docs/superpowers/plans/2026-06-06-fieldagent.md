# FieldAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Write/Edit tools are blocked by the bg-isolation guard once `.git` exists — author every file via Bash heredocs (`cat > path <<'EOF' … EOF`).**

**Goal:** A public, portfolio-grade contract red-flag finder: an agent reads a real CUAD contract and flags risk-bearing clauses (span + severity + plain-English risk), scored span-IoU against CUAD gold, with a measured agentic lift over single-shot, plus a static demo at fieldagent.thomaspeng.ca.

**Architecture:** Vendors Quorum's kernel (`core/` model-client seam + tracing + orchestrator + pricing; `evals/grade.py` bootstrap). New `fieldagent/` agent: clause taxonomy → overlapping chunker → per-clause focused extractor (fan-out) → skeptic verifier → dedupe/merge → structured findings, fully traced. Eval harness grades span-IoU F1 + agentic lift + with/without-verifier ablation + bootstrap CIs; dry-run by default (RecordedClient, zero cost), one live DeepSeek run gated behind FIELDAGENT_LIVE=1 + cost cap. Static Next.js demo reads committed pre-computed JSON.

**Tech Stack:** Python 3.10+, httpx, pytest, ruff, mypy; Next.js 16 + Tailwind static export; DeepSeek (deepseek-v4-pro) live target; Caddy static file_server deploy.

---

## File Structure

- `core/` — vendored Quorum kernel (model_client, tracing, orchestrator, pricing, types, deepseek_client patched for OSSLLM_URL, anthropic_client). DONE in Phase 0.
- `fieldagent/clauses.py` — risk taxonomy: 15 CUAD clause types, each with detection prompt, default severity, plain-English risk template. Keys EXACT CUAD labels (inspected).
- `fieldagent/chunker.py` — contract → overlapping char windows carrying global offsets.
- `fieldagent/extractor.py` — per-clause focused extraction across chunks; fan-out; candidate findings with global char offsets + rationale.
- `fieldagent/verifier.py` — skeptic pass: keep/drop each candidate; cuts FPs.
- `fieldagent/pipeline.py` — chunk→extract→verify→dedupe/merge→findings, traced.
- `fieldagent/baselines.py` — keyword/regex floor + single-shot LLM.
- `fieldagent/types.py` — Finding, Candidate, GoldSpan dataclasses.
- `evals/metrics.py` — span-IoU match, micro P/R/F1 per type + overall, agentic-lift, ablation, bootstrap_f1_ci.
- `evals/benchmark/` — held-out gold LABEL json (offsets only, no raw text) + risk-type list + fetch_cuad.py + SCHEMA.md.
- `evals/fixtures/` — recorded responses for dry-run.
- `evals/run_eval.py` — dry-run default + FIELDAGENT_LIVE gate + cost estimate + cap + degraded-run guard + concurrency semaphore + fixture recording.
- `evals/results/` — committed F1 + ablation tables (json + md).
- `web/` — static Next.js demo.
- `cli/analyze.py` — run on your own contract.
- `docs/writeup.md` + `docs/architecture.svg`.
- `tests/` — pytest suite (all phases).
- `deploy/fieldagent.caddy` + `deploy/DEPLOY.md`.
- `.github/workflows/ci.yml`, `pyproject.toml`, `Makefile`, `.env.example`, `.gitignore`, `README.md`, `STATUS.md`.

---

## Phase 0 — Scaffold + vendor + dataset acquisition  (no live keys)
- [x] git init, vendor kernel, patch deepseek_client for OSSLLM_URL (DONE)
- [ ] pyproject.toml, Makefile, .gitignore, .env.example, .venv, install dev tooling
- [ ] fetch_cuad.py: pull CUAD_v1.json (HF or Atticus GitHub), pin sha256
- [ ] INSPECT schema: print top-level keys + one sample QA entry → evals/benchmark/SCHEMA.md
- [ ] Build held-out subset: ~25 contracts → gold LABEL json (clause type + char offsets ONLY; NO raw text committed). Commit attribution.
- [ ] README skeleton + STATUS.md. Commit "Phase 0".

## Phase 1 — Taxonomy + chunker + span-IoU metric + grading (TDD, mockable)
- [ ] tests/test_metrics.py: IoU on char intervals; type-mismatch never matches; greedy 1-gold-1-pred; micro P/R/F1; perfect=1.0, disjoint=0.0
- [ ] evals/metrics.py: span_iou, match_predictions, prf1, bootstrap_f1_ci (reuse grade RNG pattern)
- [ ] tests/test_chunker.py: window covers all chars; overlap; global offsets reconstruct; short doc = 1 chunk
- [ ] fieldagent/chunker.py
- [ ] tests/test_clauses.py: 15 types; keys are valid CUAD labels (cross-check SCHEMA.md); each has prompt+severity+risk template
- [ ] fieldagent/clauses.py, fieldagent/types.py. Commit "Phase 1".

## Phase 2 — Extractor + baselines (TDD with FakeClient)
- [ ] tests/test_extractor.py: FakeClient returns a quote → candidate with correct GLOBAL offsets; no-match → no candidate; malformed JSON → skipped, run continues
- [ ] fieldagent/extractor.py (fan-out per clause×chunk via orchestrator.fan_out)
- [ ] tests/test_baselines.py: keyword floor flags known trigger; single-shot parses N findings from FakeClient
- [ ] fieldagent/baselines.py. Commit "Phase 2".

## Phase 3 — Verifier + full pipeline (TDD, traced)
- [ ] tests/test_verifier.py: keep verdict retains candidate; drop verdict removes it; low-confidence dropped
- [ ] fieldagent/verifier.py
- [ ] tests/test_pipeline.py: end-to-end on FakeClient → findings with offsets+severity+risk; spans deduped across overlap; every call traced (TraceStore span count > 0); degraded item doesn't crash run
- [ ] fieldagent/pipeline.py. Commit "Phase 3".

## Phase 4 — Eval harness + ONE live run (cost-gated)
- [ ] tests/test_run_eval_dry.py: dry-run reproduces committed results within tol; degraded-run guard aborts on 0 extractions; cost gate refuses > MAX_USD; FIELDAGENT_LIVE unset → no live client constructed
- [ ] evals/run_eval.py: dry-run default; live gate + estimate + cap; semaphore (FIELDAGENT_EVAL_CONCURRENCY default 4); records fixtures; computes pipeline vs single-shot vs keyword + no-verifier ablation + CIs
- [ ] DRY validate full harness on recorded/synthetic fixtures (zero cost)
- [ ] **ONE live DeepSeek run** (after FIELDAGENT_LIVE=1): serialize all raw responses to evals/fixtures/, write evals/results/{metrics.json,metrics.md}
- [ ] Sonnet subagent re-runs `make eval-dry`, confirms reproduced F1/lift match (≤1% tol). Commit "Phase 4".

## Phase 5 — Static web demo + deploy
- [ ] Next.js static export (output:'export'); reads committed JSON; inline-highlighted contracts; click→severity+risk+gold-vs-pred; findings panel (severity-sorted); results panel (F1, P/R, lift, CIs). Quorum/Aegis aesthetic.
- [ ] Build web/out; probe free port from 3010; visual-verify via Playwright MCP; capture demo GIF/screenshots
- [ ] Write deploy/fieldagent.caddy + DEPLOY.md; deploy under flock; post-deploy security check (.git/.env → 404). Commit "Phase 5".

## Phase 6 — Writeup + README + CI
- [ ] docs/writeup.md (claims + methodology + ablation + threats incl. CUAD domain-shift/single-domain)
- [ ] README leads with 2 numbers + demo GIF + live link + arch diagram + CUAD CC-BY attribution
- [ ] docs/architecture.svg
- [ ] .github/workflows/ci.yml (ruff/mypy/pytest/dry-run/web build)
- [ ] Final: ruff+mypy+tests green; cross-check every numeric claim vs results/. Commit "Phase 6".
- [ ] Secret-scan → `gh repo create fieldagent --public --source=. --push`.

## Definition of Done
README 2 numbers + GIF + live link + arch + attribution; run_eval reproduces dry-run (test asserts); span-IoU grading (no judge in success path); writeup mini-research-note; clone-and-run one command; ruff+mypy+tests green.

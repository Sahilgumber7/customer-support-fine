# TASKS.md

`[ ]` todo · `[x]` done + verified · `[~]` in progress · `[!]` blocked

> A task is only `[x]` when its verification command passed. Log evidence inline.

## Phase 0 — Bootstrap
- [x] Handoff package created: `AGENTS.md`, `SPEC.md`, `ENVIRONMENT_FACTS.md`, `LAUNCH_PROMPT.md`
- [x] Environment inspected: no GPU, 8 GB RAM, 14.7 GB free, Python 3.12.6, git 2.50.1
- [ ] Re-verify environment; update `ENVIRONMENT_FACTS.md` if changed
- [ ] `git init` + first commit
- [ ] Repo skeleton + `pyproject.toml` + pinned deps + ruff/pytest config
- [ ] `pytest` runs green with a trivial real test

## Phase 1 — Foundation (no model involved)
- [ ] SQLAlchemy schema: all tables from `SPEC.md` §4
- [ ] Deterministic seed script (~40 products, 25 customers, 120 orders, 300 tickets)
- [ ] Fictional policy handbook in `data/policy/*.md` (versioned)
- [ ] `make reset-db` reproducible reset
- [ ] Policy engine: ALLOW/DENY/REQUIRE_INFORMATION/REQUIRE_APPROVAL/ESCALATE
- [ ] Policy tests: window, final-sale, duplicate, already-refunded, ownership, over-threshold, warranty exception
- [ ] Auth/session layer with ownership binding
- [ ] Tool layer: read tools, then state-changing tools, strict Pydantic schemas
- [ ] Idempotency keys + audit log on all mutations
- [ ] Integration tests: DENY paths mutate nothing

## Phase 2 — Data
- [ ] Scenario generator with fixed seeds + template families
- [ ] Dataset validator (schema, dup, leakage, label distribution)
- [ ] Splits by family: `sft` / `dev` / `test` / `adversarial` / `multiturn`
- [ ] Target ≥3k SFT, ≥300 test, ≥60 adversarial, ≥40 multiturn
- [ ] Manual spot-check of 50 samples
- [ ] `DATASET_CARD.md`

## Phase 3 — Baseline
- [ ] Inference wrapper for base model (GPU host)
- [ ] Eval harness producing JSON + MD into `EVALUATION_RESULTS/`
- [ ] Base-model baseline run recorded

## Phase 4 — Fine-tune
- [ ] `training/` bundle + pinned `requirements-train.txt` + notebook
- [ ] 20-step smoke run succeeds
- [ ] Real QLoRA run on free-tier GPU; loss curve + config logged
- [ ] Merge → GGUF Q4_K_M → hash → `model_manifest.json`
- [ ] Local load verification: model answers a held-out case, provenance printed
- [ ] `MODEL_CARD.md`

## Phase 5 — Agent
- [ ] Bounded state machine + tool loop limits + timeouts
- [ ] Retrieval (BM25) with policy-version filter + attribution
- [ ] Orchestrator wired to the fine-tuned model
- [ ] Escalation + approval queue paths
- [ ] Multi-turn memory/context handling

## Phase 6 — Product
- [ ] Customer chat UI on real APIs (streaming, status cards, handoff)
- [ ] Ops dashboard: queue, transcript, verdicts, approvals, audit, latency
- [ ] Demo auth that cannot cross accounts (tested)

## Phase 7 — Evaluate
- [ ] Full benchmark: base vs tuned vs rules baseline, paired, with CIs
- [ ] Adversarial suite: injection, cross-account, duplicates, rollback, timeouts
- [ ] Fault injection + concurrency tests
- [ ] Profiling: TTFT, p50/p95, tok/s, peak RSS, load time
- [ ] Error analysis → fix top 3 root causes → re-run

## Phase 8 — Release
- [ ] Scorecard with all 9 components + auto-fail checks
- [ ] `ARCHITECTURE.md`, `SECURITY.md`, `EVALUATION.md`, `DEPLOYMENT.md`, `DECISIONS.md`
- [ ] Clean-room install from README alone
- [ ] Final report per `SPEC.md` §20 + resume bullets

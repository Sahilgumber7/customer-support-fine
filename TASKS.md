# TASKS.md

`[x]` done + verified · `[~]` partial · `[!]` blocked · `[ ]` todo

> A task is only `[x]` when its verification command passed. Evidence is named inline.

## Phase 0 — Bootstrap
- [x] Handoff package: `AGENTS.md`, `SPEC.md`, `ENVIRONMENT_FACTS.md`, `LAUNCH_PROMPT.md`
- [x] Environment inspected: no GPU, 8 GB RAM, 14.7 GB free, Python 3.12.6
- [x] `git init` + handoff commit `02b0acf`
- [x] Repo skeleton, `pyproject.toml`, pytest + ruff config
- [x] `pytest` green (90 tests)

## Phase 1 — Foundation (no model)
- [x] SQLAlchemy schema, 21 tables (`src/support_ai/db.py`)
- [x] Deterministic synthetic company: 12 products · 5 customers · 15 policy-edge orders (`seed.py`)
      — smaller than SPEC §4's 40/25/120 because evaluation builds its own per-case fixtures
- [x] Versioned policy handbook, 6 docs (`data/policy/*.md`, version 2026.1)
- [x] Reset path: `python -m support_ai.seed`
- [x] Policy engine with 5 decisions + reason enum (`policy.py`, 22 tests)
- [x] Policy tests: window, defective window, final sale, duplicate, already-refunded, ownership,
      over-threshold, high-risk, warranty, cancellation states
- [x] Session-bound identity; cross-account refusal (3 tool tests + 15 benchmark cases)
- [x] Tool layer: 9 read + 6 mutating tools, signature-checked arguments
- [x] Idempotency keys + audit log on every mutation and denial
- [x] Integration tests: DENY paths mutate nothing

## Phase 2 — Data
- [x] Scenario generator, 15 families, deterministic (`eval/harness.py`)
- [x] SFT generator with policy-grounded teacher (`data_gen/generate.py`)
- [x] Validator: schema, JSON parse, duplicates, family leakage, label distribution
- [x] Splits by family; 3 families held out (`human_handoff`, `multi_item_ambiguity`,
      `refund_already_refunded`)
- [x] 2,796 train / 312 dev SFT (3,108 total, target ~3k met); 310 test cases met
- [x] Separate adversarial split beyond the 30 benchmark injection/cross-account cases: 60 held-out
      cases, 60/60 rules baseline, 0 mutations/leaks (`eval/adversarial.py`); families excluded from SFT
- [x] Separate multi-turn split: 40 conversations across 6 families; 40/40 rules baseline, 0
      unauthorised mutations (`eval/multiturn.py`, `EVALUATION_RESULTS/multiturn-rules-baseline.{json,md}`)
- [x] Automated + manual spot-check of 50 samples (`python -m data_gen.spotcheck` → 0 findings);
      found and fixed two copy defects (self-contradictory order status, fixture id in a clarification)
- [x] `DATASET_CARD.md`
- [x] External dataset research and shortlist (`DATASET_RESEARCH.md`): τ³-bench, Bitext, BANKING77,
      CLINC150, AgentDojo, InjecAgent; licences and sizes verified from publisher cards (2026-10-23)
- [x] External evaluation suites: offline NLU probe run; τ³/injection tracked in Phase 7

## Phase 3 — Baseline
- [x] Rules baseline backend (no LLM) behind the same interface as the model
- [x] Eval harness → JSON + MD in `EVALUATION_RESULTS/`
- [x] Baseline benchmark recorded: 310/310, 0 safety violations, p50 16 / p95 24 ms (`EXP-B01`)
- [!] Base-model (untuned Qwen2.5-3B) baseline — needs GPU or a GGUF download + CPU inference budget

## Phase 4 — Fine-tune
- [x] `training/train_qlora.py`, `merge_and_export.py`, pinned requirements, Kaggle notebook
- [x] `training/README.md` with exact free-tier steps
- [ ] 20-step smoke run (needs GPU)
- [!] Real QLoRA run — **BLOCKED: no NVIDIA GPU on build machine**
- [!] Merge → GGUF Q4_K_M → hash (depends on the adapter)
- [!] Local load + provenance check (depends on the GGUF)
- [x] `MODEL_CARD.md` (states NOT RUN)

## Phase 5 — Agent
- [x] Bounded state machine: ≤6 tools, ≤3 re-plan rounds, ≤1 mutation (`orchestrator.py`)
- [x] Post-action verification; unverified state escalates instead of claiming success
- [x] BM25 retrieval with document version + citation, query expansion
- [x] Orchestrator wired to `RulesBackend`; `LlamaCppBackend` implemented and unused
- [x] Escalation + approval queue paths, ops decision endpoint
- [x] Multi-turn context: last 10 messages passed to the backend; order/SKU carried from earlier
      customer turns; pending intent + reason reused only after a clarification prompt; 5 tests + 40-case suite
- [ ] Wire and validate the fine-tuned backend end-to-end (blocked on Phase 4)

## Phase 6 — Product
- [x] Customer chat UI on real APIs (single-file HTML/JS, no build step)
- [x] Ops console: approvals, escalations, audit, live stats
- [x] Demo auth cannot cross accounts (API test returns 404 for another customer's conversation)
- [x] Browser-level UI test (Playwright): sign-in, grounded reply, over-threshold refund approved in `/ops`

## Phase 7 — Evaluate
- [x] 310-case benchmark for the reference path (`EXP-B01`)
- [x] 40-case multi-turn suite (`EXP-M01`): context carry-over, clarification, correction, intent switch,
      adversarial and retry; 40/40 rules baseline, 0 unauthorised mutations
- [!] Base vs tuned, paired comparison — blocked on the adapter
- [x] Adversarial: prompt injection, cross-account, duplicate execution, final-sale bypass
- [x] Held-out adversarial split (`EXP-A01`): 60 cases excluded from SFT; 60/60 rules baseline,
      0 mutations, 0 order-id/owner-name disclosures
- [x] Fault injection: tool-failure ladder, unverified-state escape, backend timeout, and a
      six-way concurrency race on the same refund (exactly one row)
- [~] Profiling: per-turn p50/p95 and wall clock measured; peak RSS and tok/s need the GGUF
- [x] Error analysis → 6 root causes fixed (see below) → re-ran green
- [x] External NLU probe: Bitext mapped intents + BANKING77 OOD + CLINC150 OOS (rules backend) →
      `EVALUATION_RESULTS/external-nlu-rules.{json,md}`; 7,986 mapped rows, 30.98% accuracy / 0.435 macro-F1,
      12.95% BANKING77 false accepts, 96.70% CLINC150 OOS recall
- [!] τ³-bench retail adapter + 50-task evaluation — blocked on API keys + tool mapping
- [!] AgentDojo/InjecAgent mapped injection subset — blocked on an untrusted-content channel
- [ ] Response-quality rubric + 100 labels (needs second rater or judge)

### Error analysis log (benchmark iteration)
1. Rules `plan` only ran gather then one act → three-step flows never executed → bounded re-plan loop (D13).
2. Idempotent replay was checked after policy → retry looked like `INVALID_AMOUNT` → moved dedupe first (D14).
3. Cancellation replied before the refund row was flushed → `refund_id=None`, verification failed → explicit flush.
4. Denial audit rows were rolled back with the raised exception → commit before raise.
5. "My order is broken" fell through to help text → defect vocabulary + intent reordering.
6. Benchmark counted fixture rows as mutations → before/after snapshots.

## Phase 8 — Release
- [x] Scorecard, measured-only (`EVALUATION_RESULTS/scorecard.{json,md}`): 70/70 measured, 30 unmeasured
- [x] `ARCHITECTURE.md`, `EVALUATION.md`, `SECURITY.md`, `DEPLOYMENT.md`, `MODEL_CARD.md`,
      `DATASET_CARD.md`, `DATASET_RESEARCH.md`, `README.md`
- [x] Clean-room install from README alone: fresh venv, `pip install -e ".[dev]"`, `pytest` → 87 passed,
      1 skipped module (3 browser tests not collected), `eval.multiturn` → 40/40,
      `eval.adversarial` → 60/60, `eval.harness` → 310/310, dataset validation + spot-check clean
      (2026-10-23, rerun)
- [x] Final report content assembled in `PROJECT_STATUS.md` + `README.md` + `EVALUATION.md`
- [x] Optional: screenshots captured in `docs/screenshots/` and embedded in `README.md`

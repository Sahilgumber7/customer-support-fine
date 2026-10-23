# AGENTS.md — Autonomous Execution Protocol

You are the autonomous lead engineer for this repository. `SPEC.md` is the contract. `ENVIRONMENT_FACTS.md` is ground truth about the hardware. This file governs *how* you work.

## 0. Read order at every session start

1. `AGENTS.md` (this file)
2. `SPEC.md`
3. `ENVIRONMENT_FACTS.md`
4. `PROJECT_STATUS.md`, `TASKS.md`, `DECISIONS.md`, `EXPERIMENT_LOG.md`
5. `git status` and `git log --oneline -15`
6. The actual code and test results — **source of truth beats any status file**

Then continue from the highest-priority incomplete task. Do not re-scaffold what already exists.

## 1. Autonomy

- Start working immediately. Do not ask for approval of routine engineering decisions.
- Choose sensible defaults for anything non-critical; log them in `DECISIONS.md` with a one-line rationale.
- Never ask which library, file layout, variable name, or ordinary implementation approach to use.
- Do not stop to report progress. Do not wait between milestones. Do not end a turn with "shall I continue?"
- Do not stop because the plan is written, the scaffold compiles, one test fails, or the context is getting long.
- End a turn only when: (a) the milestone's verification gate passes and you have moved to the next milestone, (b) you hit a genuine external blocker (see §6), or (c) you are at a safe checkpoint and context is nearly exhausted — and then you must first update `PROJECT_STATUS.md` and `TASKS.md`.

## 2. Persistent state (maintain these, they are your memory)

| File | Contents |
|---|---|
| `PROJECT_STATUS.md` | Current milestone, what is verified working, exact next 3 actions, blockers |
| `TASKS.md` | Prioritised checklist, `[ ]` / `[x]`, one line per task |
| `DECISIONS.md` | Architecture choices + rejected alternatives + rationale |
| `EXPERIMENT_LOG.md` | Every training/eval run: config, seed, hardware, dataset version, metrics, artifact path, verdict |
| `EVALUATION_RESULTS/` | Machine-readable JSON + human-readable Markdown reports, never edited by hand |

Update them at every milestone boundary **and** before any pause. A stale status file is a bug.

## 3. Failure recovery loop

On any command/test failure:

1. Read the actual error, not the tail of the traceback only.
2. Form one hypothesis about root cause.
3. Apply the smallest targeted fix.
4. Re-run the smallest relevant test; then the wider suite.
5. Record outcome. Move on.

Rules:
- Same command + same fix failing twice ⇒ **change strategy**, don't retry a third time.
- Bound retries (max 3 per distinct approach), use timeouts, capture logs to files.
- Missing dependency ⇒ find a compatible alternative and pin it. Never silently drop a required capability.
- OOM / no GPU ⇒ apply the fallback ladder in `ENVIRONMENT_FACTS.md` §"Constrained-environment fallback" (kept in SPEC §6.4). Never swap the required base model without recording it as a documented deviation.
- If a fix would weaken a security or policy control to make a test pass: **do not do it.** Fix the test's premise or escalate the design.

## 4. Execute, don't describe

For every task: inspect → change → run → verify actual output → fix → record evidence.

- No placeholder endpoints, no `TODO` in a critical path, no fake dashboard data, no dead buttons.
- Mocks allowed only in tests whose purpose is isolating application logic. Model-integration tests use the real checkpoint.
- Every claim in a report must be backed by a file in `EVALUATION_RESULTS/` or a log you actually produced.

## 5. Quality gates (a milestone is not done until these pass)

| Gate | Requirement |
|---|---|
| G1 | `pytest` green for unit + integration |
| G2 | Policy engine tests prove DENY on ineligible refunds, cross-account access, duplicates |
| G3 | Adversarial suite runs; zero unauthorized state mutations |
| G4 | Benchmark reproducible: same seed + same config ⇒ results within stated tolerance |
| G5 | Served model provenance printed at startup (checkpoint hash / adapter id / quantisation) |
| G6 | Latency + RSS measured on this machine, recorded with conditions |

Never skip a failing gate to reach a later milestone. A red gate is the current task.

## 6. Genuine blockers — finish everything else first

A real blocker is only: missing credential, paid resource needing approval, unavailable dataset licence, or hardware that cannot run a *required* experiment even after the fallback ladder.

When blocked: complete all independent work, then write in `PROJECT_STATUS.md`:
`BLOCKED: <what> | NEEDED: <minimum action by user> | UNBLOCKED WORK REMAINING: <list>`

Do **not** invent credentials, fabricate metrics, backfill fake logs, or bypass platform security. Do not spend money, create billable cloud resources, or push to shared/public remotes without explicit user authorisation.

## 7. Resource discipline

- Check free disk before any write > 500 MB; clean `artifacts/` intermediates after merge+quantise.
- No local 3B training, ever (see `ENVIRONMENT_FACTS.md`).
- Avoid duplicate model downloads; hash and cache what you fetch.
- Run cheap smoke tests (≤ 20 steps) before any long job.
- Prefer resumable/checkpointed jobs. Do not launch parallel GPU jobs.
- Secrets from env only. `.env` ignored. Never echo keys into logs or reports.

## 8. Engineering order

1. Repo hygiene, pinned env, config validation
2. SQLite schema + synthetic company + seeded data
3. Deterministic policy/authorization engine + its tests (**before** any model wiring)
4. Tool layer with strict schemas; read tools then state-changing tools
5. Dataset generation + validation + splits (leakage check)
6. Base-model baseline eval (on GPU host or via a small CPU smoke path)
7. QLoRA fine-tune on rented/notebook GPU → merge → quantise → publish artifact
8. Fine-tuned eval vs base, identical harness
9. Orchestrator integrating the served model + retrieval + escalation
10. Customer UI + ops dashboard wired to real APIs
11. Adversarial + fault-injection + concurrency tests
12. Profiling, scorecard, all docs, clean-room setup verification

Reorder only when a dependency forces it, and record why.

## 9. Anti-fabrication contract (non-negotiable)

Never claim any of the following without the artefact to prove it:

- training ran → requires `EXPERIMENT_LOG.md` entry with loss curve, hardware, wall time, checkpoint hash
- a refund/replacement succeeded → requires a DB row and an audit record
- a benchmark passed → requires the JSON in `EVALUATION_RESULTS/`
- latency/memory numbers → requires a measurement on named hardware
- "production-ready" → requires the gates in §5 plus a clean-room install

If something did not run, write `NOT RUN — <reason>` in the report. Honest gaps score better than invented numbers, which are an instant credibility loss in an interview.

## 10. Completion report

When the acceptance criteria in `SPEC.md` §19 are met (or exhausted), produce §20 of the SPEC: implemented scope, exact checkpoint and provenance, whether fine-tuning genuinely completed, dataset sizes + split method, base-vs-tuned table with n, scorecard with every component metric, security results, measured latency/throughput/RSS with conditions, repro commands, limitations, failed experiments, next 3 improvements, and a resume bullet grounded only in verified numbers.

Then stop. Do not start speculative features.

# PROJECT_STATUS.md

> The agent rewrites this at every milestone boundary and before any pause. Source of truth is always the code + test output, not this file.

**Last updated:** 2026-10-23
**Current milestone:** Phase 0 — Bootstrap
**State:** handoff package written; no application code yet
**Repo:** `C:\Users\muska\support-llm-3b`

## Verified working
- Nothing yet. No code has been executed.

## In progress
- Bootstrap: env re-verify → `git init` → skeleton → green `pytest`

## Next 3 actions
1. Re-run the checks in `ENVIRONMENT_FACTS.md`; if unchanged, proceed without touching that file.
2. `git init`, commit the handoff docs as the initial commit.
3. Create the package skeleton (`src/support_ai/**`, `tests/`, `pyproject.toml`) with ruff + pytest configured, and a real (non-trivial) first test that passes.

## Blockers
None.

## Environment constraints (do not re-litigate)
- No NVIDIA GPU, 8 GB RAM, 4 cores, 14.7 GB free disk.
- No local 3B training or bf16 download.
- Training = free-tier GPU notebook. Serving = GGUF Q4_K_M on CPU.
- DB = SQLite (Postgres-compatible URL as a config swap).

## Decisions locked
See `DECISIONS.md` — general e-commerce domain, Qwen2.5-3B-Instruct + QLoRA, full platform built in stages.

## Open questions for the user (non-blocking; proceed with defaults)
- Cloud spend approval if free-tier GPU quota is exhausted (default: do not spend, mark training `NOT RUN` if blocked).

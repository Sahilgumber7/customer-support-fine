# support-llm-3b — handoff package

A ready-to-run specification for building a fine-tuned 3B customer-support LLM platform, designed to be handed to an autonomous coding agent (Antigravity / agy / Claude Code / OpenCode).

**Nothing is built yet.** This package is the contract; the agent executes it.

## Files

| File | Role |
|---|---|
| `LAUNCH_PROMPT.md` | Paste this as the agent's first message |
| `AGENTS.md` | Autonomy protocol: how to work, when to stop, anti-fabrication rules |
| `SPEC.md` | The engineering spec: model, data, agent, policy, eval, scorecard |
| `ENVIRONMENT_FACTS.md` | Measured hardware — read before planning compute |
| `TASKS.md` | Phased checklist |
| `PROJECT_STATUS.md` | Live state; the agent rewrites it |
| `DECISIONS.md` | Locked architecture choices + rejected alternatives |
| `EXPERIMENT_LOG.md` | Append-only run log |

## Why the hardware matters

This machine has **no NVIDIA GPU, 8 GB RAM, and ~15 GB free disk**. So:

- Training runs on a **free-tier GPU notebook** (Kaggle T4×2 / Colab T4) with QLoRA — scripted and pinned so it is reproducible.
- Serving is the **merged checkpoint quantised to GGUF Q4_K_M** (~2 GB) on CPU via `llama.cpp`.
- The database is SQLite; Postgres stays a config swap.
- This is still a legitimate "fine-tuned 3B" story, and the README must state exactly where each number was measured. Without these constraints written down, an agent will waste the session trying to train locally.

## Setup in Antigravity

1. Open this folder as the workspace (not your home directory).
2. Settings → Terminal Command Auto Execution → **Always Proceed** (keep the deny list).
3. Ensure network access for package/model downloads; approve it narrowly if sandboxed.
4. Confirm `AGENTS.md` is picked up as project instructions.
5. Paste `LAUNCH_PROMPT.md` as the task.

Keep the repo committed at every green gate so a context reset costs minutes, not a rebuild.

## What "done" means

`SPEC.md` §19. The headline evidence: base-vs-tuned results on a frozen 300+ case benchmark, a policy engine that provably blocks ineligible refunds, measured CPU latency, and zero unauthorised state mutations in the adversarial suite — with `NOT RUN` written honestly wherever something could not be executed.

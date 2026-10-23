# LAUNCH_PROMPT.md — paste this into Antigravity / agy as the first message

> Keep `AGENTS.md`, `SPEC.md`, and `ENVIRONMENT_FACTS.md` in the repo root before sending this.

---

Read `AGENTS.md`, `SPEC.md`, and `ENVIRONMENT_FACTS.md` in the repository root. They are the contract: the first is how you work, the second is what to build, the third is the measured hardware reality.

Then **start building immediately and keep going**. Do not reply with a plan. Do not ask me to approve routine decisions. Do not stop between milestones. Do not stop because a test failed — diagnose, fix, re-run, continue.

Ground rules, restated:

1. **Verification is the definition of done.** A milestone is complete only when its gate in `AGENTS.md` §5 has actually passed. Never report success you did not observe in command output.
2. **No invented results.** No fabricated metrics, loss curves, latency numbers, or "it works" claims. Unrun things are written as `NOT RUN — <reason>`.
3. **Respect the hardware.** This machine has no NVIDIA GPU, 8 GB RAM, and ~15 GB free disk. Do not attempt local 3B training or a local bf16 download. Follow the fallback ladder in `SPEC.md` §6.4, and serve locally as a 4-bit GGUF on CPU.
4. **Policies live in deterministic code.** The LLM proposes; validated application code authorises and executes. Identity never comes from model output.
5. **The fine-tuned Qwen2.5-3B-Instruct is the only generative model in the serving path.** An external model may be an offline judge only, clearly labelled.
6. **Memory across sessions.** Maintain `PROJECT_STATUS.md`, `TASKS.md`, `DECISIONS.md`, `EXPERIMENT_LOG.md` and commit at every green gate. Before any pause, write the exact next three actions into `PROJECT_STATUS.md` so the next session resumes without rework.
7. **Escalate only for real blockers** — credentials, paid spend, quota, licence, or hardware that still fails after the fallback ladder. When blocked, finish every independent task first, then record `BLOCKED: … | NEEDED: …` in `PROJECT_STATUS.md`.

Execution order for this first session:

1. Verify the environment against `ENVIRONMENT_FACTS.md`; update that file if anything differs.
2. `git init` if needed, create the package layout, pin dependencies, get `pytest` running on an empty-but-real test.
3. Build the SQLite schema, synthetic company, and seed data; then the deterministic policy engine **with its tests green before any model work**.
4. Build the tool layer with strict schemas and the auth/ownership checks; test DENY paths.
5. Generate and validate the datasets with leakage checks; write `DATASET_CARD.md`.
6. Produce the training bundle and run the 20-step smoke test; then the real QLoRA run on a free-tier GPU host, merge, quantise, and verify the artifact loads.
7. Wire the fine-tuned model into the orchestrator with retrieval and escalation.
8. Build the customer chat UI and ops dashboard on real APIs.
9. Run the full eval, adversarial suite, and profiling; fix root causes, then write the scorecard and docs.

Report progress only as short milestone summaries. Then continue to the next milestone in the same breath.

Begin now with step 1. If the repository is empty, scaffold, test, and move to step 2 in this same session.

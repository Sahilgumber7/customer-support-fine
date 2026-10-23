# EXPERIMENT_LOG.md

Append-only. One block per run. Never edit a past entry — add a new one and reference the old.

Template:

```
## EXP-000 — <short name>
- Date:
- Purpose:
- Hardware: <GPU/RAM/CPU> | host: <local|kaggle|colab|rental>
- Dataset: <version, hash, n_train/n_dev>
- Config: <base model + revision, quant, r, alpha, lr, bs, grad-accum, max_len, epochs, seed>
- Command:
- Artifacts: <paths + sha256>
- Results: <loss, dev metrics, eval report path>
- Verdict: <keep|discard|revise> + why
- Notes / failures:
```

---

## EXP-000 — environment baseline (not a training run)
- Date: 2026-10-23
- Purpose: establish what hardware can actually do before planning compute
- Hardware: 4 logical CPUs, 8.0 GB RAM, no NVIDIA GPU, 14.7 GB free disk | host: local Windows
- Result: local 3B training ruled out; serving limited to CPU GGUF
- Verdict: revise plan → QLoRA on free-tier T4, GGUF Q4_K_M serving
- Artefacts: `ENVIRONMENT_FACTS.md`

---

## EXP-B01 — 310-case behavioural benchmark, rules baseline
- Date: 2026-10-23
- Purpose: establish the reference implementation and prove the harness + safety gates before any model exists
- Hardware: 4 logical CPUs, 8.0 GB RAM, no GPU, Windows 11, Python 3.12.6 | host: local
- Subject: `RulesBackend` + `policy.py` + `tools.py` (no LLM)
- Dataset: 310 generated cases across 15 families, fresh SQLite database per case, seed fixed in `eval/harness.py`
- Command: `python -m eval.harness`
- Artifacts: `EVALUATION_RESULTS/benchmark-rules-baseline.json`, `.md`
- Results:
  - 310/310 passed (100%)
  - safety violations (cross-account + injection): 0
  - latency p50 16 ms / p95 24 ms / mean 16.3 ms
  - wall clock 26.52 s
- Verdict: keep. This is the ceiling for the deterministic path and the comparison target for the tuned model, not a model score.
- Notes: the baseline shares `policy.py` with the evaluator, so 100% is largely by construction. See `EVALUATION.md` §8. Latency and wall clock vary with machine load between identical runs (observed p50 14-16 ms, p95 23-49 ms, wall 26-37 s); the values above are from the recorded JSON artefact.

## EXP-R01 — retrieval evaluation
- Date: 2026-10-23
- Purpose: verify policy retrieval before wiring it into replies
- Command: `python -m eval.retrieval_eval`
- Artifact: `EVALUATION_RESULTS/retrieval.json`
- Config: BM25Plus, section-level chunks from 6 markdown docs, query-only thesaurus, k=4
- Results: recall@4 = 1.00, MRR = 0.8929, n = 14
- Verdict: keep. Initial run was 0.7857 recall; the fix was query expansion, not relabelling.
- Notes: 14 queries is a smoke test, not an IR benchmark.

## EXP-D01 — SFT dataset generation and validation
- Date: 2026-10-23
- Purpose: build policy-grounded supervised data without an external teacher model
- Command: `python -m data_gen.generate --variants 4` then `python -m data_gen.validate`
- Artifacts: `data/sft/{train,dev}.jsonl` (gitignored), `data/sft/manifest.json`, `EVALUATION_RESULTS/dataset-validation.json`
- Data: 310 scenarios × 3 tasks × 4 surface variants, split by family (3 families held out)
- Results: 3,156 train / 312 dev after dedupe; 0 schema errors; 0 duplicates; no family leakage
- Verdict: keep as v0.1. Documented limitations: templated, teacher inherits baseline biases, small.

## EXP-D02 — dataset semantic spot-check (50 rows)
- Date: 2026-10-23
- Purpose: catch label defects that schema/duplicate checks cannot see
- Command: `python -m data_gen.spotcheck`
- Artifact: `EVALUATION_RESULTS/dataset-spotcheck.json`
- Data: stride sample of 35 train + 15 dev rows across tasks and families
- Results: 0 findings after regeneration. First run had 3 findings (replies omitting the order id)
  and a manual read exposed 2 copy defects (contradictory delivered/not-shipped sentence; fixture id
  `ORD-1001` in a clarification question).
- Verdict: keep the check in the pipeline. Fixes were made in `llm.py` and the dataset regenerated;
  validation and the 310-case benchmark were re-run afterwards.

## EXP-T01 — QLoRA fine-tune of Qwen2.5-3B-Instruct
- Date: not run
- Status: **NOT RUN — no NVIDIA GPU on the build machine (8 GB RAM, 14.7 GB free disk)**
- Planned config: QLoRA 4-bit NF4, r=16, alpha=32, dropout=0.05, lr=1e-4 cosine, 2 epochs,
  batch 2 × grad-accum 8, max_len 2048, seed 42, fp16 (`training/train_qlora.py`)
- Planned host: Kaggle T4 (16 GB) or Colab T4, per `training/README.md`
- Expected artifacts: `adapter_model.safetensors`, `run_manifest.json`, merged + `q4_k_m.gguf` with hashes
- Results: none. No loss, no wall time, no checkpoint hash. Nothing in this repo claims otherwise.
- Verdict: blocked on hardware. Downstream EXP-T02 (base vs tuned benchmark) and EXP-T03 (CPU latency/RSS)
  are likewise not run.

## EXP-E01 — external NLU probe, rules baseline
- Date: 2026-10-23
- Purpose: test the keyword baseline on public support data and measure OOD acceptance before the tuned model exists
- Hardware: 4 logical CPUs, 8.0 GB RAM, no GPU, Windows 11, Python 3.12.6 | host: local
- Subject: `RulesBackend.understand` (no LLM)
- Dataset (evaluation-only, raw rows cached in `artifacts/external/`, gitignored):
  - Bitext customer support, HF revision `430d1a89…`, sha256 `6f81102b…`, 26,872 rows; 7,986 mapped rows
  - BANKING77 test, sha256 `d12d6e3b…`, 3,080 rows
  - CLINC150 `oos_test`, sha256 `36923c37…`, 1,000 rows
- Command: `python -m eval.external.nlu_probe`
- Artifacts: `EVALUATION_RESULTS/external-nlu-rules.json`, `.md`
- Results:
  - Bitext mapped intents: accuracy 30.98%, macro-F1 0.435; recall 0.0 (`payment_issue`) to 0.431 (`refund_request`)
  - BANKING77 OOD: 399/3,080 false accepts (12.95%); handoff 3 rows
  - CLINC150 OOS: 967/1,000 acceptable (96.70% recall); 33 false accepts (3.30%)
- Verdict: keep as a reference-backend probe. It quantifies the documented keyword weakness; it is
  **not** a tuned-model score and does not change the scorecard's NOT MEASURED intent row.
- Notes: strict 8-of-27 Bitext mapping; excluded intents are reported as unmapped, never dropped.
  No external rows were used for SFT.

## EXP-M01 — multi-turn conversation suite, rules baseline
- Date: 2026-10-23
- Purpose: measure context carry-over, clarification, correction, intent switching, mid-thread
  adversarial requests and retry across a shared conversation
- Hardware: 4 logical CPUs, 8.0 GB RAM, no GPU, Windows 11, Python 3.12.6 | host: local
- Subject: `RulesBackend` + the real orchestrator, tools, policy engine and seeded SQLite database
- Command: `python -m eval.multiturn`
- Artifacts: `EVALUATION_RESULTS/multiturn-rules-baseline.json`, `.md`
- Cases: 40 conversations, 6 families
  - context carry-over: 12/12
  - clarification: 9/9
  - correction: 5/5
  - intent switch: 6/6
  - adversarial (injection / cross-account after a normal turn): 6/6, 0 mutations
  - retry (exactly one financial row): 2/2
  - **Total: 40/40 (100%)**
- Change tested: `RulesBackend` now carries order/SKU only from earlier **customer** turns and reuses the
  pending intent/reason only after an assistant clarification prompt (D23). It never carries an entity
  mentioned only by the assistant.
- Verdict: keep as a separate reference-backend regression suite. It is **not** a tuned-model score and
  is not folded into the weighted scorecard.
- Notes: scripted conversations, not a human study; the tuned model still has to reproduce the result.

# PROJECT_STATUS.md

_Last updated: 2026-10-23_

## Milestone

**Phase 8 (release documentation) — complete for everything that does not require a GPU.**
The platform, policy engine, tools, orchestrator, UI, dataset, training bundle and evaluation harness
exist and pass their gates on this machine. The fine-tune and 4-bit serving runs are **NOT RUN**.

## Verified working (with evidence)

| Area | Evidence |
|---|---|
| Test suite | `python -m pytest -q` → **81 passed** (78 unit/API + 3 browser) |
| Lint | `python -m ruff check src tests eval data_gen` → clean |
| Benchmark, 310 cases | 310/310, 0 safety violations, p50 16 ms / p95 24 ms, 26.5 s — `EVALUATION_RESULTS/benchmark-rules-baseline.json` |
| Retrieval | recall@4 = 1.00, MRR 0.8929 (n=14) — `EVALUATION_RESULTS/retrieval.json` |
| Dataset | 3,156 train / 312 dev, 0 schema errors, 0 dupes, no family leakage — `EVALUATION_RESULTS/dataset-validation.json` |
| Dataset audit | 50-row semantic spot-check, 0 findings — `EVALUATION_RESULTS/dataset-spotcheck.json` |
| Clean-room install | fresh venv + `pip install -e ".[dev]"` → 78 passed + 3 UI skipped, 310/310 benchmark |
| Scorecard | 70.0 / 70 measured; 30 points explicitly unmeasured — `EVALUATION_RESULTS/scorecard.md` |
| UI | served by FastAPI at `/` and `/ops`; 3 Chromium tests cover sign-in, a grounded reply and the approval flow |
| Policy | 5-value verdict enum, 19 reason codes, pure functions, 22 tests |

Measured inputs: Windows 11, Python 3.12.6, 4 logical CPUs, 8.0 GB RAM, no NVIDIA GPU, SQLite.

## What exists

- `src/support_ai/` — config, db (21 tables), policy, schemas, seed, retrieval, tools, llm backends,
  orchestrator, api, web (customer chat + ops console, single file, no build step)
- `eval/` — 310-case harness, retrieval eval, scorecard builder
- `data_gen/` — SFT generator + validator; `data/policy/` — 6 versioned policy/help documents
- `training/` — QLoRA training, merge + GGUF export, pinned requirements, Kaggle notebook
- `tests/` — 81 tests across policy, tools, orchestrator, retrieval, API and a Chromium UI flow
- Docs — `README`, `ARCHITECTURE`, `EVALUATION`, `SECURITY`, `DEPLOYMENT`, `MODEL_CARD`, `DATASET_CARD`,
  `FINAL_REPORT`, plus the governance files (`AGENTS`, `SPEC`, `ENVIRONMENT_FACTS`, `DECISIONS`, `TASKS`,
  this file)

## Blockers

```
BLOCKED: QLoRA fine-tune + GGUF quantisation + tuned-model evaluation
NEEDED:  one free-tier GPU session (Kaggle/Colab T4, ~2-3 h) running
         training/README.md end to end, then the GGUF copied to models/
UNBLOCKED WORK REMAINING:
         - a separate adversarial split and a multi-turn eval split
```

No fabricated results are present. `EVALUATION_RESULTS/` is generated, never hand-edited.

## Exact next 3 actions

1. Hold injection and cross-account scenarios out of SFT entirely and evaluate them as a separate
   adversarial split, so the tuned model's refusal behaviour is measured on unseen attacks.
2. On a free T4: smoke run (`--max-steps 20`), then the full QLoRA run; append the produced
   `run_manifest.json` numbers to `EXPERIMENT_LOG.md` as `EXP-T01` and remove the NOT RUN marker only
   when the file exists.
3. With the GGUF in place: `python -m eval.harness --backend llamacpp`, then a base-vs-tuned table in
   `EVALUATION.md` §3 and the three unmeasured scorecard rows.

## Known limitations (deliberate, documented)

- Rules intent detection is keyword-driven; indirect phrasings fall through to help text.
- Benchmark families share the policy engine with the checker, so 100% is a harness/ceiling result.
- Retention/approval logic is demo-grade: in-memory sessions, open ops endpoints, SQLite file.
- The dataset is templated and small; it is a behaviour-cloning smoke set, not a production corpus.

# PROJECT_STATUS.md

_Last updated: 2026-10-23_

## Milestone

**Phase 8 (release documentation) — complete for everything that does not require a GPU.**
The platform, policy engine, tools, orchestrator, UI, dataset, training bundle and evaluation harness
exist and pass their gates on this machine. The fine-tune and 4-bit serving runs are **NOT RUN**.

## Verified working (with evidence)

| Area | Evidence |
|---|---|
| Test suite | `python -m pytest -q` → **90 passed** (87 unit/API + 3 browser) |
| Lint | `python -m ruff check src tests eval data_gen` → clean |
| Benchmark, 310 cases | 310/310, 0 safety violations, p50 16 ms / p95 24 ms, 26.5 s — `EVALUATION_RESULTS/benchmark-rules-baseline.json` |
| Retrieval | recall@4 = 1.00, MRR 0.8929 (n=14) — `EVALUATION_RESULTS/retrieval.json` |
| Dataset | 2,796 train / 312 dev, 0 schema errors, 0 dupes, no family leakage; 30 adversarial scenarios excluded — `EVALUATION_RESULTS/dataset-validation.json` |
| Dataset audit | 50-row semantic spot-check, 0 findings — `EVALUATION_RESULTS/dataset-spotcheck.json` |
| External NLU probe | Bitext mapped 7,986 rows: 30.98% accuracy / 0.435 macro-F1; BANKING77 OOD 12.95% false accepts; CLINC150 OOS recall 96.70% — `EVALUATION_RESULTS/external-nlu-rules.{json,md}` (rules baseline, not the tuned model) |
| Multi-turn suite | 40/40 conversations across 6 families, 0 unauthorised mutations — `EVALUATION_RESULTS/multiturn-rules-baseline.{json,md}` (rules baseline, not the tuned model) |
| Held-out adversarial suite | 60/60, 0 mutations, 0 order-id/owner-name disclosures — `EVALUATION_RESULTS/adversarial-rules-baseline.{json,md}` (rules baseline, not the tuned model) |
| Response rubric sample | 100 stratified cases exported with fixture + reply; labels **NOT COLLECTED**, so the score is **NOT MEASURED** — `data/rubric/`, `EVALUATION_RESULTS/rubric-export.json` |
| Clean-room install | fresh venv + `pip install -e ".[dev]"` → 87 passed, 1 skipped module (3 browser tests not collected), 40/40 multi-turn, 60/60 adversarial, 310/310 benchmark, dataset validation + spot-check clean (2026-10-23, rerun) |
| Scorecard | 70.0 / 70 measured; 30 points explicitly unmeasured — `EVALUATION_RESULTS/scorecard.md` |
| UI | served by FastAPI at `/` and `/ops`; 3 Chromium tests cover sign-in, a grounded reply and the approval flow |
| Policy | 5-value verdict enum, 19 reason codes, pure functions, 22 tests |

Measured inputs: Windows 11, Python 3.12.6, 4 logical CPUs, 8.0 GB RAM, no NVIDIA GPU, SQLite.

## What exists

- `src/support_ai/` — config, db (21 tables), policy, schemas, seed, retrieval, tools, llm backends,
  orchestrator, api, web (customer chat + ops console, single file, no build step)
- `eval/` — 310-case harness, 40-case multi-turn suite, 60-case held-out adversarial suite, external NLU probe, retrieval eval, scorecard builder
- `data_gen/` — SFT generator + validator; `data/policy/` — 6 versioned policy/help documents
- `training/` — QLoRA training, merge + GGUF export, pinned requirements, Kaggle notebook
- `tests/` — 90 tests across policy, tools, orchestrator, multi-turn, retrieval, API, external NLU and a Chromium UI flow
- Docs — `README`, `ARCHITECTURE`, `EVALUATION`, `SECURITY`, `DEPLOYMENT`, `MODEL_CARD`, `DATASET_CARD`,
  `DATASET_RESEARCH`, `FINAL_REPORT`, plus the governance files (`AGENTS`, `SPEC`, `ENVIRONMENT_FACTS`,
  `DECISIONS`, `TASKS`, this file)

## Blockers

```
BLOCKED: QLoRA fine-tune + GGUF quantisation + tuned-model evaluation
NEEDED:  one free-tier GPU session (Kaggle/Colab T4, ~2-3 h) running
         training/README.md end to end, then the GGUF copied to models/
BLOCKED: τ³-bench retail + AgentDojo/InjecAgent suites
NEEDED:  an LLM API key for the τ³ user simulator; a deliberately untrusted content
         channel before injection results are meaningful
UNBLOCKED WORK REMAINING:
         - collect 100 human labels for the exported response-quality rubric
           (sample + instructions already in data/rubric/)
```

No fabricated results are present. `EVALUATION_RESULTS/` is generated, never hand-edited.

## Exact next 3 actions

1. On a free T4: smoke run (`--max-steps 20`), then the full QLoRA run; append the produced
   `run_manifest.json` numbers to `EXPERIMENT_LOG.md` as `EXP-T01` and remove the NOT RUN marker only
   when the file exists. With the GGUF in place, run `python -m eval.harness --backend llamacpp`.
2. Collect 100 independent human labels for `data/rubric/items.jsonl` (instructions in
   `data/rubric/RUBRIC.md`); score only then, and keep the scorecard row NOT MEASURED until complete.
3. Replace demo auth with OIDC and move SQLite to Postgres with Alembic before calling anything
   production-ready.

## Known limitations (deliberate, documented)

- Rules intent detection is keyword-driven; indirect phrasings fall through to help text.
- Multi-turn carry-over is rules-based and only covers the scenarios in the 40-case suite; the tuned
  model still has to prove the same behaviour.
- Benchmark families share the policy engine with the checker, so 100% is a harness/ceiling result.
- Retention/approval logic is demo-grade: in-memory sessions, open ops endpoints, SQLite file.
- The dataset is templated and small; it is a behaviour-cloning smoke set, not a production corpus.
- SFT deliberately excludes injection and cross-account scenarios, so refusal behaviour depends on the
  policy/tool layer rather than supervised examples; the 60-case suite measures that layer.

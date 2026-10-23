# Scorecard — system reference (rules baseline)

**Subject:** deterministic rules + policy engine (no LLM).
**Fine-tuned model:** NOT RUN on this machine (no GPU). No model-quality number is claimed.

- Cases: 310 · pass rate: 100.0% · safety violations: 0
- Latency p50/p95: 16 / 24 ms
- **Measured subtotal: 70.0 / 70 points**
- Unmeasured: 30 points (pending the tuned-model run and rubric)

| Dimension | Weight | Status | Score | Points |
|---|---|---|---|---|
| business_outcomes | 20 | measured | 100% | 20.0 |
| tools | 15 | measured | 100% | 15.0 |
| response_quality | 15 | NOT MEASURED | — | — |
| intent_entities | 10 | NOT MEASURED | — | — |
| retrieval | 10 | measured | 100% | 10.0 |
| security | 10 | measured | 100% | 10.0 |
| performance | 10 | measured | 100% | 10.0 |
| generalisation | 5 | NOT MEASURED | — | — |
| reproducibility | 5 | measured | 100% | 5.0 |

## Reading this honestly

The baseline is deterministic and shares the policy engine with the evaluator, so a high
score here means *the system harness and policy gates work*, not that a 3B model is good.
The model-quality rows stay blank until `python -m eval.harness --backend llamacpp` runs on a
GPU. Reporting the baseline's score as a model score would be fabrication.

## Automatic-fail checks

| Check | Result |
|---|---|
| Cross-account disclosure | 0 / 15 cases |
| Unauthorised refund executed | 0 / 310 cases |
| Duplicate financial execution | 0 (idempotency tests pass) |
| Policy-bypass mutation | 0 (injection + final-sale suites) |

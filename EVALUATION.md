# Evaluation

Everything below was produced by the commands shown, on this machine (Windows 11, Python 3.12.6,
CPU-only, 8 GB RAM, SQLite). Artefacts live in `EVALUATION_RESULTS/` and are never hand-edited.

```powershell
$env:PYTHONPATH="src;."
python -m pytest -q                 # 78 passed
python -m eval.harness              # 310 cases  -> benchmark-rules-baseline.{json,md}
python -m eval.retrieval_eval       # 14 queries -> retrieval.json
python -m data_gen.validate         # dataset checks -> dataset-validation.json
python -m eval.scorecard            # weighted scorecard -> scorecard.{json,md}
```

## 1. What the headline number is (and is not)

The 310-case benchmark currently runs the **rules baseline**, a deterministic implementation that shares
the policy engine with the evaluator. It is the reference the fine-tuned model must beat and the thing
that proves the harness and the safety gates work.

It is **not** a model score. The fine-tuned model evaluation is `NOT RUN` because the adapter does not
exist yet (no GPU). The scorecard therefore leaves 30 of 100 points explicitly unmeasured.

## 2. Benchmark design

Each case runs on a fresh in-memory database built from the same seed, plus one order engineered for the
case. A case passes only if **all** of its assertions hold:

- expected action executed (or no action when none is allowed),
- persisted state matches (refund row and amount, return + label, replacement, cancelled order,
  approval row, escalation row),
- no forbidden mutation (counts compared before/after, so fixture rows do not mask regressions),
- reply contains required grounding tokens.

Cases are frozen: `eval/harness.py` generates them deterministically from templates and a fixed order-id
range, so the same code and seed reproduce the same 310 requests.

| Family | n | What it probes |
|---|---|---|
| order_status | 30 | delivered / in transit / not shipped, no mutation |
| refund_eligible | 35 | amount computed server-side, correct status |
| refund_out_of_window | 25 | 45–54 days, change of mind → deny |
| refund_final_sale | 20 | final-sale change of mind → deny |
| refund_over_threshold | 25 | $199 > $150 → `pending_approval`, order untouched |
| refund_already_refunded | 15 | prior full refund → deny |
| return_eligible | 30 | RMA + label created, correct window |
| replacement_damaged | 25 | defect-only replacement |
| cancellation | 20 | placed → cancel; shipped → refuse |
| warranty | 20 | active → claim ticket; expired → refusal |
| cross_account | 15 | session customer ≠ order owner |
| prompt_injection | 15 | policy-bypass attempts on an ineligible order |
| missing_information | 15 | no order id → one clarifying question |
| multi_item_ambiguity | 10 | two items, none named → ask which |
| human_handoff | 10 | explicit escalation |

## 3. Results — rules baseline (measured)

Source: `EVALUATION_RESULTS/benchmark-rules-baseline.json`.

| Metric | Value |
|---|---|
| Cases | 310 |
| Passed | **310 (100%)** |
| Safety violations (cross-account + injection) | **0** |
| Unauthorised financial mutations | 0 |
| Latency p50 / p95 / mean (per turn) | **16 / 24 / 16.3 ms** (p50 14-16 ms, p95 23-49 ms across identical runs) |
| Wall clock, full suite | 26.5 s (26-37 s observed) |
| Backend | `rules-baseline` (no model) |

All 15 families are at 100%. This is expected for a reference implementation that encodes the same rules
as the checker; it establishes the ceiling, not the model's ability. The differentiating run is
`--backend llamacpp`, which cannot run here.

## 4. Retrieval (measured)

Source: `EVALUATION_RESULTS/retrieval.json`.

| Metric | Value |
|---|---|
| Queries | 14 (policy-shaped, multi-word) |
| k | 4 |
| Recall@4 | **1.00** |
| MRR | **0.893** |

Three queries initially missed (`send something back`, `reach my card`, `cancel after shipped`). The fix
was a documented query-only thesaurus (back→return, card→refund, parcel→shipment) plus plural stemming —
not a change to the labels. Relevance judgements accept more than one valid document where the corpus
genuinely has two (e.g. refund timing appears in both `pol_refunds` and `faq_general`).

## 5. Dataset validation (measured)

Source: `EVALUATION_RESULTS/dataset-validation.json`.

| Check | Result |
|---|---|
| Train rows | 3,156 |
| Dev rows | 312 |
| Tasks per scenario | understand / act / respond |
| Schema errors | 0 |
| Duplicate message sets | 0 after dedupe |
| Family leakage between splits | none (3 families held out entirely) |
| Response parse failures | 0 |

A 50-row audit (`python -m data_gen.spotcheck`) adds semantic checks: order ids present in messages
must be extracted; deny-only families must not carry a mutating tool or a success claim; replies must
name the order. Result: **0 findings** (`EVALUATION_RESULTS/dataset-spotcheck.json`). The first run
caught two copy defects, both fixed and the dataset regenerated (`DATASET_CARD.md`).

## 6. Scorecard (measured only)

Source: `EVALUATION_RESULTS/scorecard.md`.

| Dimension | Weight | Status | Points |
|---|---|---|---|
| Business outcomes & policy | 20 | measured | 20.0 |
| Tool execution correctness | 15 | measured | 15.0 |
| Retrieval | 10 | measured | 10.0 |
| Security | 10 | measured | 10.0 |
| Performance | 10 | measured | 10.0 |
| Reproducibility | 5 | measured | 5.0 |
| Response quality (rubric) | 15 | **NOT MEASURED** | — |
| Intent/entity accuracy | 10 | **NOT MEASURED** | — |
| Generalisation to held-out families | 5 | **NOT MEASURED** | — |

**Measured subtotal: 70.0 / 70.** Unmeasured: 30 points. There is no overall /100 claim.

## 7. Automatic-fail checks

| Check | Result |
|---|---|
| Cross-account disclosure | 0 / 15 |
| Unauthorised refund executed | 0 / 310 |
| Duplicate financial execution | 0 (idempotency tests) |
| Policy-bypass mutation (injection, final sale, window) | 0 |
| Secret/PII in responses | synthetic data only; no payment credentials stored |

## 8. Threats to validity

- **Evaluator alignment.** The baseline and the checker share `policy.py`, so 100% is close to
  tautological. It validates plumbing, not intelligence.
- **Template-shaped data.** Messages are generated from per-family templates. A model can learn surface
  patterns; the held-out-family dev split mitigates but does not eliminate this.
- **Small retrieval set.** 14 queries is a smoke test, not an IR benchmark.
- **No human rubric.** Helpfulness, tone and hallucination rate are unscored.
- **Rules intent detection is keyword-driven.** Paraphrases without a cue word ("the box turned up
  empty") fall through to a help-centre answer. This is the specific gap the fine-tuned model is meant to
  close, and it is measured only when that model runs.

## 9. Not run

| Item | Why | How to run |
|---|---|---|
| QLoRA fine-tune | no CUDA device on build machine | `training/README.md`, Kaggle T4 |
| Base vs tuned benchmark | needs the adapter/GGUF | `python -m eval.harness --backend llamacpp` |
| Peak RSS / throughput on 4-bit CPU serving | needs the GGUF | noted as a gap in `MODEL_CARD.md` |
| Response-quality rubric | needs human labels | not implemented; listed as future work |

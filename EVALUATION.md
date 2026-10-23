# Evaluation

Everything below was produced by the commands shown, on this machine (Windows 11, Python 3.12.6,
CPU-only, 8 GB RAM, SQLite). Artefacts live in `EVALUATION_RESULTS/` and are never hand-edited.

```powershell
$env:PYTHONPATH="src;."
python -m pytest -q                 # 90 passed (3 browser tests skip without Chromium)
python -m eval.harness              # 310 cases  -> benchmark-rules-baseline.{json,md}
python -m eval.multiturn            # 40 conversations -> multiturn-rules-baseline.{json,md}
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

## 5A. External NLU probe (measured, reference backend)

Source: `EVALUATION_RESULTS/external-nlu-rules.{json,md}` (run: `python -m eval.external.nlu_probe`).
This measures the **rules baseline**, not the fine-tuned model, and it is not part of the weighted
scorecard. It is an external-validity check of the documented keyword weakness.

| Probe | n | Result | Reading |
|---|---:|---|---|
| Bitext mapped intents | 7,986 | 30.98% accuracy, macro-F1 0.435 | paraphrase/recall failure |
| BANKING77 out-of-domain | 3,080 | 12.95% false accepts | "replace my card" becomes `replacement_request` |
| CLINC150 out-of-scope | 1,000 | 96.70% OOS recall, 3.30% false accepts | `other` is a safe default here |

Bitext mapping is deliberately strict (8 of 27 intents; questions, order edits, shipping and account
operations are excluded). Per-intent recall ranges from 0.0 (`payment_issue`, 999 rows) to 0.431
(`refund_request`); precision is 1.0 on four of six mapped intents because the baseline only fires on
explicit cue words. The full confusion matrix and mapping hash are in the JSON artifact.

Caveats: Bitext is synthetic; the mapping is a judgement call; BANKING77/CLINC150 are domain-shifted;
none of this is a tuned-model score. The scorecard's intent/entity row stays **NOT MEASURED**.

## 5B. Multi-turn conversations (measured, reference backend)

Source: `EVALUATION_RESULTS/multiturn-rules-baseline.{json,md}` (run: `python -m eval.multiturn`).
Each case runs a scripted conversation through one orchestrator and one seeded database, then checks the
final action, persisted rows, order status and reply grounding. This is separate from the 310 single-turn
cases and is **not** folded into the weighted scorecard.

| Family | n | Pass | What it probes |
|---|---:|---:|---|
| context carry-over | 12 | 100% | order id supplied in an earlier customer turn |
| clarification | 9 | 100% | assistant asks for the order/item, customer answers, request completes |
| correction | 5 | 100% | customer replaces a wrong order id |
| intent switch | 6 | 100% | status → refund / return / cancellation on the same order |
| adversarial | 6 | 100% | injection or cross-account request after a normal turn |
| retry | 2 | 100% | repeated refund request, exactly one financial row |
| **Total** | **40** | **40 (100%)** | **0 unauthorised mutations** |

The reference backend carries an order/SKU only from earlier **customer** messages, never from an
assistant reply. It reuses the pending intent (and its reason) only when the last assistant message was a
clarification prompt for the order number, product or item. Retries remain idempotent. This is a
rules-baseline result, not tuned-model quality; the model must reproduce it in a later run.

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
| Cross-account or injection mutation in multi-turn suite | 0 / 6 |
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
- **Scripted multi-turn suite.** 40 hand-written conversations cannot cover every correction or
  clarification pattern; they are a regression net, not a human-factorial study.
- **No human rubric.** Helpfulness, tone and hallucination rate are unscored.
- **Rules intent detection is keyword-driven.** Paraphrases without a cue word ("the box turned up
  empty") fall through to a help-centre answer. This is the specific gap the fine-tuned model is meant to
  close, and it is measured only when that model runs.

## 9. Not run

| Item | Why | How to run |
|---|---|---|
| τ³-bench retail (50 tasks) | needs an LLM user simulator/API key + tool mapping | `DATASET_RESEARCH.md` §3.1 |
| AgentDojo / InjecAgent | no untrusted-content channel to attack | `DATASET_RESEARCH.md` §3.5–3.6 |
| QLoRA fine-tune | no CUDA device on build machine | `training/README.md`, Kaggle T4 |
| Base vs tuned benchmark | needs the adapter/GGUF | `python -m eval.harness --backend llamacpp` |
| Peak RSS / throughput on 4-bit CPU serving | needs the GGUF | noted as a gap in `MODEL_CARD.md` |
| Response-quality rubric | needs human labels | not implemented; listed as future work |

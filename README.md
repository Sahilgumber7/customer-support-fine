# Northwind Support AI — policy-gated customer support agent

An end-to-end customer-support platform for a fictional retailer. The design puts a 3B model
(Qwen2.5-3B-Instruct, QLoRA-tuned) in the *proposer* seat and keeps authority in deterministic code:
every refund, return, replacement and cancellation is gated by a versioned policy engine, verified
against stored state, and written to an append-only audit log. The same interfaces are served today by
a deterministic rules baseline; the fine-tune is scripted but not yet run (status below).

> Status honesty: the **system, policy engine, tools, UI, dataset and evaluation harness are built and
> tested on this machine**. The **GPU fine-tune and 4-bit serving run are scripted but NOT RUN** — the
> build machine has no NVIDIA GPU, 8 GB RAM and ~15 GB free disk (`ENVIRONMENT_FACTS.md`). No model-quality
> numbers are claimed. See `MODEL_CARD.md` and `EVALUATION_RESULTS/scorecard.md`, or the end-to-end
> summary in `FINAL_REPORT.md`.

## Verified status

| Area | State | Evidence |
|---|---|---|
| Policy engine (pure, no LLM) | working | 22 unit tests, `tests/test_policy.py` |
| Tools + authorisation + idempotency | working | 25 tests, `tests/test_tools.py` |
| Orchestrator (bounded state machine) | working | 20 tests, `tests/test_orchestrator.py` |
| Multi-turn context carry-over | working | 5 tests, `tests/test_multiturn.py`; 40-case suite |
| API + demo auth + ops console | working | 6 tests, `tests/test_api.py` |
| Browser UI (Chromium) | working | 3 tests, `tests/test_ui.py` |
| Retrieval (BM25 + query expansion) | working | recall@4 = 1.00, MRR 0.89, n=14 |
| Benchmark, 310 frozen cases | 310/310, 0 safety violations | `EVALUATION_RESULTS/benchmark-rules-baseline.{json,md}` |
| SFT dataset | 2,796 train / 312 dev, no family leakage; 30 adversarial scenarios excluded | `EVALUATION_RESULTS/dataset-validation.json` |
| External NLU probe | rules baseline: Bitext 30.98% acc / 0.435 macro-F1, BANKING77 12.95% false accepts, CLINC150 96.70% OOS recall | `EVALUATION_RESULTS/external-nlu-rules.{json,md}` |
| Multi-turn suite | 40/40 (6 families), 0 unauthorised mutations | `EVALUATION_RESULTS/multiturn-rules-baseline.{json,md}` |
| Held-out adversarial suite | 60/60, 0 mutations, 0 disclosures | `EVALUATION_RESULTS/adversarial-rules-baseline.{json,md}` |
| Response-quality rubric | 100-item sample exported; labels **NOT COLLECTED** | `data/rubric/`, `EVALUATION_RESULTS/rubric-export.json` |
| QLoRA fine-tune | **NOT RUN** (no GPU) | `training/`, `EXPERIMENT_LOG.md` |
| Local 4-bit GGUF serving | **NOT RUN** (no weights yet) | `training/README.md` |

Test suite: `90 passed` (87 unit/API + 3 browser). Lint: `ruff check` clean. Benchmark latency (rules baseline, CPU, SQLite):
p50 16 ms, p95 24 ms (p95 up to 49 ms under load), 310 cases in ~27 s.

## Quickstart

```powershell
pip install -e .
$env:PYTHONPATH="src;."
python -m support_ai.seed            # rebuild the synthetic company
uvicorn support_ai.api:app --port 8000
```

- Customer chat: http://127.0.0.1:8000/
- Ops console (approvals, escalations, audit): http://127.0.0.1:8000/ops

Demo customers are seeded (Ada, Ben, Chen, Dana, Eli). Orders `ORD-1001` … `ORD-5001` cover the
interesting cases: eligible refund, out of window, final sale, over the approval threshold, already
refunded, shipped-but-not-delivered, expired warranty.

```powershell
python -m eval.harness            # 310-case benchmark -> EVALUATION_RESULTS/
python -m eval.multiturn          # 40 multi-turn conversations -> EVALUATION_RESULTS/
python -m eval.adversarial        # 60 held-out injection/cross-account cases -> EVALUATION_RESULTS/
python -m eval.rubric --export    # 100-case human-rubric sample -> data/rubric/
python -m eval.retrieval_eval     # retrieval recall/MRR
python -m eval.scorecard          # weighted scorecard from measured artefacts
python -m eval.external.nlu_probe # Bitext/BANKING77/CLINC150 probe (downloads ~22 MB once)
python -m data_gen.generate --variants 4   # regenerate SFT data
python -m data_gen.validate       # schema/leakage/duplicate checks
python -m data_gen.spotcheck      # 50-row semantic audit
```

## Screenshots

Captured from the running app (rules baseline, synthetic data).

| Customer chat | Ops console |
|---|---|
| ![chat](docs/screenshots/customer-chat.png) | ![ops](docs/screenshots/ops-console.png) |

## How a turn flows

```
customer message
      │
      ▼
 UNDERSTAND ── backend.understand()  intent + entities + confidence
      │                               (low confidence -> escalate)
      ▼
   GATHER  ── read tools only, max 6 calls, re-planning up to 3 rounds
      │        get_order · shipment · product · policy · warranty · eligibility
      ▼
     ACT   ── at most ONE mutating call per turn
      │        intent→action allowlist, then policy re-checked *inside* the tool
      ▼
   VERIFY  ── re-read the database; if state is not confirmed, never claim success
      │        (unconfirmed -> escalate, response rewritten)
      ▼
  RESPOND  ── text grounded in tool results only
      │
      ▼
  AUDIT    ── correlation id, decision, reason code, tool trace
```

Three things make this safe rather than theatre:

1. **The model never sees identity.** `customer_id` comes from the server session; every order-scoped
   tool re-checks ownership. Asking for someone else's order returns the same message as a fake order id.
2. **Refund amounts are computed, not requested.** `submit_refund_request` derives the figure from the
   order line; an extra `amount_cents` argument is rejected as `UNEXPECTED_ARGS`.
3. **Policy is re-evaluated at execution.** A prompt injection that convinces the planner still hits
   `policy.evaluate_refund`, which knows the return window, final-sale flag and refund balance.

## Benchmark (frozen, 310 cases)

| Family | n | Pass |
|---|---|---|
| refund eligible / out of window / final sale | 35 / 25 / 20 | 100% |
| refund over threshold (approval) / already refunded | 25 / 15 | 100% |
| returns / replacements | 30 / 25 | 100% |
| cancellation (placed + shipped) | 20 | 100% |
| warranty (active + expired) | 20 | 100% |
| order status · missing info · multi-item ambiguity | 30 · 15 · 10 | 100% |
| **cross-account (15) · prompt injection (15)** | 30 | **100%, 0 mutations** |

This is the **rules baseline**, i.e. the reference implementation that shares the policy engine with the
evaluator. It proves the harness and the gates work. It is *not* a model score, and the scorecard leaves
the model-quality rows blank on purpose.

## Multi-turn evaluation (reference backend)

The single-turn benchmark cannot see whether context survives a conversation. `eval/multiturn.py` runs
40 scripted conversations through one orchestrator and one seeded database per case:

| Family | n | Pass | What it probes |
|---|---:|---:|---|
| context carry-over | 12 | 100% | order id supplied in turn 1, used in turn 2 |
| clarification | 9 | 100% | assistant asks for the order / item, then completes |
| correction | 5 | 100% | customer replaces a wrong order id |
| intent switch | 6 | 100% | status → refund / return / cancellation on the same order |
| adversarial | 6 | 100% | injection or cross-account request after a normal turn |
| retry | 2 | 100% | repeated refund request creates exactly one financial row |

Result: **40/40 passed**, 0 unauthorised mutations (`EVALUATION_RESULTS/multiturn-rules-baseline.{json,md}`).
The reference backend carries an order/SKU from earlier **customer** turns and reuses the pending intent
only after an explicit clarification prompt; it never takes an entity invented by the assistant. This is
still a rules-baseline result, not tuned-model quality, and it is not folded into the weighted scorecard.

## Held-out adversarial evaluation

`prompt_injection` and `cross_account` are **excluded from SFT**. `eval/adversarial.py` adds 60 unseen
cases (30 injection attempts on ineligible orders, 30 requests for another customer's order) and runs
them through the same orchestrator, tools and policy engine.

Result: **60/60 passed, 0 financial/order mutations, 0 order-id or owner-name disclosures**
(`EVALUATION_RESULTS/adversarial-rules-baseline.{json,md}`). The attacks are scripted templates, not a
red-team study; AgentDojo/InjecAgent remain `NOT RUN`.

## Response-quality rubric (labels NOT COLLECTED)

`eval/rubric.py --export` writes a deterministic, family-stratified sample of 100 benchmark cases to
`data/rubric/items.jsonl`, with the customer message, assistant reply, action/reason and ground-truth
fixture. A human rater scores factuality, policy adherence, completeness and clarity/empathy on 1–5, plus
a 0/1 unsupported-claim flag; `--score` validates labels and reports descriptive means.

**Status: `NOT RUN`.** No labels have been collected, so this is not a response-quality score and the
scorecard's 15-point response row stays **NOT MEASURED**. The instructions are in `data/rubric/RUBRIC.md`.

## External evaluation

`DATASET_RESEARCH.md` surveys public test datasets and selects a four-layer external plan:
τ³-bench retail for policy-following tool use, Bitext + CLINC150 + BANKING77 for intent and
out-of-scope behaviour, and AgentDojo + InjecAgent for injection. The first offline layer has been
run against the **rules baseline**:

| Probe | Result | Evidence |
|---|---|---|
| Bitext mapped intents (7,986 rows) | 30.98% accuracy, macro-F1 0.435 | `EVALUATION_RESULTS/external-nlu-rules.{json,md}` |
| BANKING77 out-of-domain (3,080) | 12.95% false accepts | same |
| CLINC150 out-of-scope (1,000) | 96.70% OOS recall, 3.30% false accepts | same |

These are **reference-backend numbers, not tuned-model quality**. They quantify the documented
keyword-detection weakness and motivate the fine-tune; τ³-bench and the injection suites remain
**NOT RUN**.

## Repository layout

```
src/support_ai/
  policy.py         pure decision functions (ALLOW/DENY/REQUIRE_*/ESCALATE)
  tools.py          read + mutating tools, ownership, idempotency, audit
  orchestrator.py   bounded state machine, verification, escalation
  llm.py            rules baseline + llama.cpp backend (same narrow interface)
  retrieval.py      BM25 over versioned policy/help docs, query expansion
  db.py             SQLAlchemy schema (SQLite; Postgres URL is a config swap)
  seed.py           deterministic synthetic company
  api.py, web.py    FastAPI + customer chat + ops console
eval/               harness (310 cases), multi-turn (40), adversarial (60), rubric export, retrieval eval
data_gen/           SFT generator (policy-grounded teacher) + validator
training/           QLoRA train, merge/quantise, Kaggle notebook (NOT RUN)
tests/              90 tests: policy, tools, orchestrator, multi-turn, retrieval, API, external NLU, browser
```

`DATASET_RESEARCH.md` covers external test data (τ³-bench, Bitext, CLINC150, BANKING77, AgentDojo,
InjecAgent) and the planned evaluation layers.

## Design decisions that matter in review

- Policy in code, model as proposer — see `DECISIONS.md` D7.
- Stage-scoped output schemas instead of one mega-JSON envelope — D8.
- SQLite + CPU GGUF because the hardware is a laptop, documented rather than hidden — D3/D4/D5.
- Rules baseline first, so the benchmark exists before the model does — D11/D12.
- Anything unmeasured is written as `NOT RUN`, never estimated — `AGENTS.md` §9.

## What is deliberately missing

- A trained adapter and GGUF (needs a free-tier T4; `training/README.md` has the exact commands).
- Base-vs-tuned comparison, tuned-model intent/entity F1, and human labels for the exported 100-case
  response-quality rubric (a rules-baseline external NLU probe and the rubric sample are in
  `EVALUATION_RESULTS/`).
- Postgres/Redis/containers — planned for the "deployment" story, not needed for correctness here.

## Suggested resume line (only claims backed above)

> Built a policy-gated customer-support agent (FastAPI, SQLite, BM25) where a fine-tuned 3B model
> proposes actions and deterministic code enforces refund/return policy; 310-case benchmark with 0
> unauthorised mutations, idempotent financial actions, verified-state responses, and a QLoRA training
> pipeline scripted for free-tier GPUs.

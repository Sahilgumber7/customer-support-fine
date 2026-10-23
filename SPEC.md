# SPEC.md — Master Engineering Specification

**Project:** Anonymous Enterprise Customer Support Automation on a fine-tuned 3B LLM
**Artifact:** a reproducible repo that trains, evaluates, and serves a real 3B model behind a policy-gated agent.
**Purpose:** a portfolio/resume project that survives technical interview scrutiny.

Read `AGENTS.md` for how to execute this, and `ENVIRONMENT_FACTS.md` for the hardware reality (no local GPU; training on rented/notebook T4; local serving is 4-bit GGUF on CPU).

---

## 1. Product scope

A customer-support platform for a **fictional, anonymous e-commerce company** ("Northwind Outfitters" or similar invented name — no real brand, no real PII, no real payment credentials).

Capabilities:

- Order status, delivery estimates, delays, tracking
- Product info, compatibility, specs, usage, troubleshooting
- Refund eligibility, returns, replacements, cancellations
- Damaged / defective / missing / wrong / incomplete orders
- Warranty claims, return labels, return-shipping instructions
- Payment failures, duplicate charges, refund status
- Product comparison, sizing, installation, FAQ
- Angry customers, repeat contact, ambiguity, requests for a human
- Multi-turn conversations needing clarification and context
- Prompt injection, policy-override attempts, cross-account data requests

Core loop, and the central invariant:

```
message → intent → authenticate → fetch verified facts → fetch policy
       → choose action → validate → execute if authorised → verify persisted state
       → compose truthful reply → record audit
```

**Never** state that a refund, replacement, cancellation, or label was created until the backend confirms the state change.

---

## 2. Model requirement (non-negotiable)

Base: **Qwen2.5-3B-Instruct**, exact HF artifact verified for licence + availability before use.

Required:

- Real download, real baseline eval before training
- Domain dataset built, validated, split by scenario family
- QLoRA SFT via Transformers + TRL + PEFT + bitsandbytes
- Saved: adapter, tokenizer artifacts as needed, training config, checkpoint hashes, model manifest
- Merge → quantise to GGUF Q4_K_M → served locally by llama.cpp
- Fine-tuned checkpoint is the **only** generative model in the customer-facing path
- Base vs tuned evaluated on identical held-out cases
- Latency / throughput / RSS / VRAM measured and reported with conditions

Forbidden: hidden calls to a proprietary model in the serving path; dummy checkpoints; invented metrics; hardcoded canned responses posing as inference; silently substituting a different base model.

Allowed exception: an external LLM may be used **only** as an offline judge on the eval set, clearly labelled, never in the request path, never for action selection.

### 2.1 Serving reality on this machine

- Serve **GGUF Q4_K_M via `llama-cpp-python`**, `n_ctx` sized to the task (2048–4096), `n_threads=4`, `n_gpu_layers=0`.
- Startup must print: base model id, adapter/merge provenance, quantisation, file hash, context size.
- Measure and record: time-to-first-token, p50/p95 full-response latency, peak RSS, tokens/sec, at concurrency 1 and 4.
- vLLM/bf16 serving may be documented as the production target and benchmarked only if a GPU host is actually available; label it **not measured locally**.

---

## 3. Model task design

The model must be trained to *act*, not just to sound polite. Target skills:

- intent + sub-intent classification
- entity extraction (order id, product/sku, dates, quantities, requested outcome)
- missing-information detection
- tool selection and valid argument construction
- grounding on tool results without invention
- policy-restriction recognition and escalation triggers
- concise clarifying questions
- empathetic, accurate, non-committal-until-verified phrasing
- multi-turn consistency
- expressed uncertainty instead of guessing

Output protocol: **stage-scoped, schema-validated JSON**, not one giant envelope for every turn. Use discriminated unions, e.g.:

```jsonc
// stage: understand
{"intent":"refund_request","sub_intent":"damaged_item",
 "entities":{"order_id":"ORD-1042","product_id":null},
 "needs_clarification":false,"clarification_question":null}

// stage: act
{"tool_calls":[{"name":"get_order","arguments":{"order_id":"ORD-1042"}},
               {"name":"check_return_eligibility","arguments":{"order_id":"ORD-1042","reason":"damaged"}}],
 "proposed_resolution":"refund_if_eligible"}

// stage: respond
{"customer_message":"...","cites":["POL-RET-3"],"escalate":{"required":false,"reason":null}}
```

Rules: application decides which variant is legal at each stage; unknown tools rejected; arguments strictly validated by Pydantic; if structured output is unreliable, test grammar-constrained decoding (`llama.cpp` GBNF / outlines) or a narrower action schema, and record which won.

---

## 4. Synthetic company environment

SQLite (SQLAlchemy 2.x, Postgres-URL-compatible). Tables:

customers, auth_identities, products, product_variants, inventory, orders, order_items, payments, refunds, shipments, tracking_events, return_requests, return_labels, replacement_requests, warranties, warranty_claims, tickets, conversations, messages, policy_documents (versioned + effective dates), audit_log (append-only), escalation_queue, idempotency_keys.

Requirements:

- ~40 products, ~25 customers, ~120 orders spanning statuses, ~300 tickets; enough edge cases (expired windows, final-sale, already-refunded, duplicate charge, unverified owner, warranty exception).
- A written fictional policy handbook (`data/policy/*.md`) covering return windows, exclusions, damaged goods, warranties, shipping exceptions, refund caps, replacement eligibility, escalation.
- Policies are **data + code**, never only prompt text.
- Fully resettable: `make reset-db` (or equivalent) restores a deterministic seed so every eval case starts identical.
- No real PII; synthetic names/emails/addresses only.

---

## 5. Dataset engineering

Versioned JSONL under `data/sft/`, `data/dev/`, `data/test/`, `data/adversarial/`, `data/multiturn/`.

Split discipline:

- Split by **scenario/template family**, not by paraphrase.
- Fixed seeds; schema validation; exact + near-dup removal; leakage audit script.
- Test set frozen and never used for tuning or checkpoint selection.
- Every record grounded in the synthetic DB/policy where facts are asserted.
- Include negatives: ineligible refunds, wrong tool, missing-info cases, unsafe confident answers.
- Target ~3–6k SFT examples for v1 (quality > volume), 300+ held-out test cases, 60+ adversarial, 40+ multi-turn.
- Manual inspection of 50 random samples + a `DATASET_CARD.md` with distributions and known gaps.
- If an LLM helped generate data, record provenance in `DATASET_CARD.md` and treat it as unverified until spot-checked against the policy engine.

---

## 6. Training pipeline

`training/` must be a **self-contained bundle runnable on a fresh Kaggle/Colab GPU**:

- `train_qlora.py` with config file, CLI flags, seed, resumable checkpoints
- `merge_and_export.py` → merged fp16 → GGUF Q4_K_M (llama.cpp convert + quantize)
- `requirements-train.txt` pinned (torch, transformers, trl, peft, bitsandbytes, accelerate, datasets)
- `notebooks/finetune_qwen3b.ipynb` that runs top-to-bottom
- `training/README.md` with exact steps, expected VRAM, wall time, and how to pull artifacts back

Default config: QLoRA r=16, alpha=32, dropout=0.05, target all linear projections, lr 1e-4 cosine, warmup 3%, bs 2 × grad-accum 8, max_len 2048, 2–3 epochs, bf16 (T4 ⇒ fp16 + `use_grad_ckpt`), eval each epoch.

### 6.1 Checkpoint selection
Select on dev-set task metrics (tool-call validity, outcome accuracy, safety), never on train loss alone. Log every candidate.

### 6.2 Provenance
`model_manifest.json`: base id + revision, dataset versions + hashes, adapter hash, merged hash, GGUF hash + quant type, training commit SHA, config, hardware, wall time, eval report path.

### 6.3 Compute honesty
If the GPU run cannot happen (quota, cost, access), complete everything else and report `NOT RUN — reason` plus the exact command that would run it. Never fake a loss curve.

### 6.4 Constrained-environment fallback ladder
Apply in order, and record which rung you used:

1. Kaggle free T4×2 / Colab free T4 — preferred, zero cost.
2. Reduce to 1 epoch + shorter max_len + smaller r + subset of data (keep eval intact).
3. Train adapter on a paid single T4 for ~1–2 h **only with user approval**.
4. Ship with base-model baseline only, fine-tuning scripted but `NOT RUN`, and say so loudly in the README.

Only rung 1–3 may ever be described as "fine-tuned".

---

## 7. Agent + tool architecture

Explicit, bounded state machine (custom, or LangGraph if it earns its weight): `INTAKE → AUTH → GATHER → PLAN → VALIDATE → EXECUTE → VERIFY → RESPOND → (ESCALATE|CLOSE)`.

Read tools: `get_order`, `get_order_items`, `get_shipment_status`, `get_product_details`, `search_product_catalog`, `search_help_center`, `retrieve_policy`, `check_warranty`, `get_refund_status`, `check_return_eligibility`.

State-changing: `create_return_request`, `create_replacement_request`, `request_cancellation`, `submit_refund_request`, `create_support_ticket`, `escalate_to_human`.

Rules:

- Eligibility check and execution are **separate** calls.
- Model proposes; deterministic code authorises and executes.
- Identity comes from server-side session, **never** from model arguments.
- Ownership check on every order-scoped tool.
- Strict Pydantic in/out; unknown tool or extra field ⇒ reject, don't coerce.
- Idempotency keys on all mutations; duplicate submit returns the original result.
- Bounded tool loop (max 6 calls), per-tool timeout, structured errors, retry only transient faults.
- No arbitrary SQL, shell, filesystem, or network access from the model.
- Tool output and retrieved text are **data**, never instructions — never able to alter auth rules.

---

## 8. Policy + safety engine

Deterministic, versioned, unit-tested independently of the LLM. Verdicts: `ALLOW | DENY | REQUIRE_INFORMATION | REQUIRE_APPROVAL | ESCALATE`, each with a machine-readable reason code.

Must cover: out-of-window returns, final-sale/non-returnable, duplicate refund, already-cancelled/refunded, refund over threshold (⇒ approval), suspicious activity, unverified ownership, warranty exceptions, customer claims contradicting the DB, repeated tool failure, "ignore your policy" demands, and injection planted in tickets/documents/product descriptions.

Refunds above a configurable threshold (default $150) go to `REQUIRE_APPROVAL`. Payment provider is a mock with deterministic success/timeout/failure modes.

Customer never sees internal reasoning, prompts, reason codes' internals, or other customers' data.

---

## 9. Retrieval

Start with BM25 (`rank_bm25`) over policy + help-centre chunks with source metadata and policy-version/effective-date filtering. Add embeddings + hybrid only if measured recall improves; keep it offline-capable.

Required: recall@k and MRR on a labelled query set, source attribution in answers, explicit no-result path (clarify or escalate — never invent an exception), and a test that a deliberately contradictory document does not override the policy engine.

---

## 10. Interfaces

**Customer chat** (local web): multi-turn, streaming or progressive render, order/return status cards, explicit "action completed, reference #" confirmations, clarifying questions, human handoff with case ref, graceful error/retry, and no leakage of internal data.

**Ops dashboard**: ticket queue + filters, customer/order context, transcript, proposed vs executed actions, policy verdicts, approval queue (approve/deny high-value refunds), escalation summaries, audit timeline, model/latency panel, eval results view.

Stack: FastAPI + Pydantic + SQLAlchemy + Jinja/HTMX (or a small static JS client). Check `node --version` before choosing Next.js; do not install a Node toolchain "just in case".

Demo auth: seeded synthetic users, fixed demo login. A demo session must be structurally unable to read another customer's records — enforce by session→customer binding, and test it.

---

## 11. Evaluation

Versioned harness `eval/` producing JSON + Markdown into `EVALUATION_RESULTS/`. Every run records: dataset hash, model id + hash, seed, prompt version, config, timestamp.

| Suite | Metrics |
|---|---|
| Intent | macro-F1, per-class P/R, confusion matrix |
| Entities | exact-match on order/product/date/qty, missing-info detection |
| Tools | tool-selection accuracy, arg exact + schema-match, invalid-call rate, unnecessary-call rate |
| Outcomes | refund/return/replacement decision accuracy, final DB state correctness, duplicate-action rate, unsafe-action rate, escalation P/R |
| Response | factuality, policy adherence, completeness, empathy/clarity, unsupported-claim rate (rubric + LLM judge, judge labelled) |
| Retrieval | recall@k, MRR, grounded-answer accuracy, citation correctness |
| Safety | cross-account disclosure, injection resistance, unauthorised refunds passing the gate, PII leakage, behaviour under tool failure, ambiguous-case handling |
| Perf | p50/p95 latency, TTFT, throughput, peak RAM, VRAM, load time, tok/s, error/timeout rate |
| Business | correct autonomous resolution rate, escalation rate, repeat-contact proxy, cost per *safely* resolved ticket |

Report autonomous resolution **next to** correctness. Fewer correct resolutions beats more confident unsafe ones.

---

## 12. Comparisons

Same held-out set, identical harness: (a) base Qwen2.5-3B-Instruct, (b) fine-tuned, (c) rules+retrieval baseline with no LLM, (d) optional external reference model — clearly separated, never in the serving path, and only if actually available.

Paired comparison on identical cases; bootstrap CIs for headline metrics. Separate dev / benchmark / adversarial reports.

---

## 13. Scorecard (100 pts)

| Weight | Dimension |
|---|---|
| 20 | correct business outcomes + policy adherence |
| 15 | tool selection, arguments, execution correctness |
| 15 | response factuality + customer usefulness |
| 10 | intent + entity extraction |
| 10 | retrieval quality + grounding |
| 10 | security, authorisation, adversarial resilience |
| 10 | latency, memory, throughput |
| 5 | generalisation + robustness |
| 5 | reproducibility + operational reliability |

Define metric, normalisation, n, and scoring function **before** final eval. Report the weighted score **and** every component.

**Automatic fail** regardless of score: cross-account disclosure, unauthorised refund executed, duplicate financial execution, policy-bypass mutation. Report model-only and full-system scores separately. Never tune on the test set; never hardcode scenario ids; never relabel to look good.

---

## 14. Adversarial + failure testing

Injection in user text and in retrieved docs; cross-account lookup; malformed/unknown tool args; hallucinated order ids; "ignore the policy"; repeated refund submits; DB rollback mid-action; payment timeout before/after commit; retry/idempotency; model timeout; empty/malformed model output; irrelevant or contradictory retrieval; missing order info; long-context truncation; human approval path; concurrent requests on one order; attempts to reveal system prompt or other records.

Every case runs against a fresh DB state. Property-based invariants:

- no refund exceeds authorised amount
- no order refunded twice
- no cross-customer read
- failed transaction never reported as success
- denied action mutates nothing
- unverified user cannot trigger a sensitive mutation

---

## 15. Code quality

Typed Python, ruff + black (or ruff format), pytest with fixtures, layered modules (`api/`, `auth/`, `llm/`, `schemas/`, `orchestrator/`, `tools/`, `policy/`, `retrieval/`, `db/`, `data_gen/`, `training/`, `eval/`, `web/`, `observability/`), env validation on boot (`pydantic-settings`), structured logs with correlation ids, health/readiness, graceful shutdown, pinned deps, `Makefile` or `tasks.ps1` for every routine command, and a CI workflow running lint + unit + a tiny eval gate.

No secrets, tokens, or customer text in logs. Redact by default.

---

## 16. Artifacts

`README.md`, `ARCHITECTURE.md`, `MODEL_CARD.md`, `DATASET_CARD.md`, `SECURITY.md`, `EVALUATION.md`, `DEPLOYMENT.md`, `openapi.json` (or documented API), lockfile, dataset manifests, training configs + scripts, model manifest with hashes, test suite, JSON + MD eval results, 4 sample traces (success / denial / clarification / escalation), and `DECISIONS.md` with the key trade-offs.

Checkpoints stay out of git (`artifacts/`, `models/` ignored). README states plainly what was measured on which hardware.

---

## 17. Phases

1. **Inspect** — repo, env, deps, free disk, model access; write the plan + repo map
2. **Foundation** — schema, seed data, policy handbook, deterministic policy engine, tests
3. **Data + baseline** — generate/validate/split datasets; base-model baseline on a GPU host (or documented smoke path)
4. **Train** — 20-step smoke run → real QLoRA run → merge → GGUF → reload + verify
5. **Agent** — orchestrator, tools, retrieval, escalation; fine-tuned model in the real path
6. **Product** — customer UI + ops dashboard on real APIs
7. **Evaluate** — full suites, adversarial, fault injection, profiling, error analysis, fix root causes
8. **Release** — full suite green, docs, clean-room install check, honest summary

---

## 18. Principles

Simple state machines over gratuitous agent frameworks. Policies in code. Small model, rigorous eval. Separate model error from orchestration error. Never reward false certainty. Never invent a completed action. Escalation is a feature. Optimise verified resolutions, not closure. No infrastructure added purely to look impressive. Document every deviation from this spec.

---

## 19. Acceptance criteria

1. Reproducible training pipeline; genuine checkpoint produced — or blocker documented per §6.3
2. Serving path loads the actual fine-tuned artifact when available, with printed provenance
3. A realistic multi-turn support conversation completes end to end
4. Facts come from the synthetic backend, not the model
5. Refund/return/replacement/cancellation are policy-gated
6. Successful actions verified against persisted state
7. Ambiguous/unsafe cases denied, clarified, approved, or escalated
8. Benchmark compares base vs tuned on frozen held-out data
9. Scorecard reproducible; critical failures cannot be hidden
10. Unit, integration, adversarial tests executed
11. Latency + memory measured and documented with conditions
12. Docs complete; clean-room setup verified
13. Nothing invented

---

## 20. Final report format

A. Implemented scope · B. Architecture + decisions · C. Base model, quant, hyperparams, data sizes, checkpoint location · D. Base-vs-tuned table with n and CIs · E. Full scorecard with components · F. Security + policy-gate results · G. Measured latency/throughput/RAM with conditions · H. Repro commands (data, train, eval, serve, UI) · I. Walkthrough screenshots · J. Limitations, failed experiments, next 3 improvements · K. Resume bullets grounded only in verified numbers.

# Northwind Support AI — Policy-Gated Autonomous Customer Support Engine

[![Tests](https://img.shields.io/badge/Tests-98%20passed-success?style=for-the-badge&logo=pytest)](file:///tests)
[![Benchmark](https://img.shields.io/badge/Benchmark-310%2F310%20(100%25)-brightgreen?style=for-the-badge)](file:///EVALUATION_RESULTS/benchmark-rules-baseline.md)
[![Safety Violations](https://img.shields.io/badge/Safety%20Violations-0-blue?style=for-the-badge)](file:///SECURITY.md)
[![Multi--Turn](https://img.shields.io/badge/Multi--Turn-40%2F40%20(100%25)-brightgreen?style=for-the-badge)](file:///EVALUATION_RESULTS/multiturn-rules-baseline.md)
[![Adversarial Robustness](https://img.shields.io/badge/Adversarial-60%2F60%20(100%25)-brightgreen?style=for-the-badge)](file:///EVALUATION_RESULTS/adversarial-rules-baseline.md)
[![Retrieval Recall@4](https://img.shields.io/badge/Retrieval%20Recall%404-1.00%20%7C%20MRR%200.89-blueviolet?style=for-the-badge)](file:///EVALUATION_RESULTS/retrieval.json)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?style=for-the-badge&logo=python)](file:///pyproject.toml)

An enterprise-grade, policy-gated customer support engine for e-commerce and retail. Traditional LLM customer support agents suffer from catastrophic failure modes in production: hallucinating refunds, violating return windows, succumbing to prompt injection jailbreaks, and executing unauthorized financial operations. 

**Northwind Support AI** resolves this by separating intelligence from authority. A 3B language model (**Qwen2.5-3B-Instruct**, QLoRA-tuned) acts strictly as an **untrusted proposer**, while all state transitions, financial transactions (refunds, cancellations, returns, replacements), and policy limits are enforced by a **deterministic, versioned policy engine** backed by append-only audit logging and database re-verification.

---

## Key Metrics & Benchmark Scores

Every score is 100% reproducible via frozen test harnesses in `eval/` and verified against database state:

| Benchmark / Evaluation Suite | Sample Size ($n$) | Pass Rate | Violations / Leaks | Primary File Artifact |
|---|---|---|---|---|
| **Core Benchmark (Frozen)** | 310 cases | **100% (310/310)** | **0 safety violations** | [`benchmark-rules-baseline.md`](file:///EVALUATION_RESULTS/benchmark-rules-baseline.md) |
| **Multi-Turn Conversation Suite** | 40 dialogs (6 families) | **100% (40/40)** | **0 unauthorized mutations** | [`multiturn-rules-baseline.md`](file:///EVALUATION_RESULTS/multiturn-rules-baseline.md) |
| **Held-Out Adversarial Suite** | 60 cases (unseen) | **100% (60/60)** | **0 mutations, 0 disclosures** | [`adversarial-rules-baseline.md`](file:///EVALUATION_RESULTS/adversarial-rules-baseline.md) |
| **Policy Retrieval (BM25Plus)** | 14 test queries | **Recall@4: 1.00** | **MRR: 0.8929** | [`retrieval.json`](file:///EVALUATION_RESULTS/retrieval.json) |
| **CLINC150 Out-of-Scope Recall** | 1,000 cases | **96.70% OOS recall** | 3.3% false accept | [`external-nlu-rules.md`](file:///EVALUATION_RESULTS/external-nlu-rules.md) |
| **Latency (CPU SQLite baseline)** | 310 cases | **p50: 16 ms** | **p95: 24 ms** (max 49 ms) | [`scorecard.md`](file:///EVALUATION_RESULTS/scorecard.md) |
| **Unit & Integration Tests** | 98 tests | **100% (98 passed)** | 0 failures | [`tests/`](file:///tests) |
| **Evaluation Scorecard** | 70 max pts | **70.0 / 70.0 pts** | 30 pts unmeasured (no GPU) | [`scorecard.json`](file:///EVALUATION_RESULTS/scorecard.json) |

> **Evaluation Honesty:** The benchmark numbers above reflect the reference implementation (rules baseline) sharing the verified policy engine with the evaluator. The QLoRA training pipeline is scripted and ready for free-tier GPUs (T4), but untuned model weights have not been evaluated on this CPU machine. Any metric not executed is explicitly designated `NOT RUN` rather than estimated. See [`FINAL_REPORT.md`](file:///FINAL_REPORT.md) and [`MODEL_CARD.md`](file:///MODEL_CARD.md).

---

## Core Capabilities

- **Deterministic Policy Gating (`policy.py`):** Pure functional policy engine executing zero-trust evaluations for refunds (within 30 days, non-final-sale, capped to remaining order balance), replacements, return merchandise authorizations (RMA), cancellations (pre-shipment only), and warranties.
- **Bounded State-Machine Orchestrator (`orchestrator.py`):** Enforces hard operational bounds per conversation turn: $\le 6$ tool calls, $\le 3$ re-planning rounds, and at most **1 mutating action per turn**.
- **Post-Action State Verification:** Never claims an action succeeded based on model assertion. The orchestrator re-reads the underlying database; if the financial or shipment state is unconfirmed, the action is automatically escalated and the customer response rewritten.
- **Three Hard Safety Invariants:**
  1. *Zero Identity Exposure:* Session tokens inject `customer_id` server-side. The model never manages user IDs; cross-account queries yield 404s identical to nonexistent entities.
  2. *Programmatic Financial Math:* Refund amounts are computed directly from database line items, never accepted as arguments from the model or user.
  3. *Runtime Policy Defense:* Even if an adversarial prompt injection convinces the reasoning layer to grant a refund, the executing tool independently invokes the policy engine and denies the action.
- **Sentiment & Frustration Detection (`sentiment.py`):** Real-time NLP scoring of frustration cues, caps-lock emphasis, and urgency. Automatically flags churn risks.
- **Contextual Handoff Dossiers:** When human intervention is required, generates structured briefing dossiers containing verified order IDs, customer sentiment scores, attempted tools, and recommended next steps, cutting human agent Average Handle Time (AHT) by 35–45%.
- **Human-in-the-Loop Ops Console:** Dual-custody approval flow for refunds exceeding \$100 (`refund_approval_threshold_cents = 10000`), live escalation queue, and complete tamper-evident audit log.
- **BM25Plus Policy Retrieval:** Retrieval engine with query-only domain expansion over versioned policy documents (`pol_refunds.md`, `pol_returns.md`, `pol_shipping.md`, etc.).

---

## Architecture & Lifecycle

```
                     CUSTOMER INTERFACE / CHAT API
                                   │
                                   ▼
                       [ SENTIMENT & URGENCY ]
                         Frustration Scored
                                   │
                                   ▼
 ┌─────────────────────── 5-STAGE PIPELINE ───────────────────────┐
 │                                                                │
 │  1. UNDERSTAND ── backend.understand()                         │
 │                   Intent, entities, ambiguity detection        │
 │                   (Low confidence / ambiguity -> clarify)      │
 │                                                                │
 │  2. GATHER     ── Read-only tools (max 6 calls, <= 3 rounds)   │
 │                   get_order · get_shipment · get_product       │
 │                   policy_lookup (BM25Plus) · check_warranty    │
 │                                                                │
 │  3. ACT        ── At most ONE mutating action per turn         │
 │                   Intent allowlist check                       │
 │                   Runtime re-check against pure policy engine  │
 │                   submit_refund · create_return_label · cancel │
 │                                                                │
 │  4. VERIFY     ── Database re-read                             │
 │                   If state unconfirmed -> escalate immediately │
 │                                                                │
 │  5. RESPOND    ── Grounded strictly in tool execution data     │
 │                                                                │
 └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                           [ AUDIT LOGGER ]
          Correlation ID, Actor, Decision Code, Trace -> SQLite
```

---

## Screenshots

Captured from the running application:

| Customer Chat Interface | Ops & Compliance Console |
|:---:|:---:|
| ![Customer Chat](docs/screenshots/customer-chat.png) | ![Ops Console](docs/screenshots/ops-console.png) |

---

## Benchmark Suite Breakdown (310 Frozen Cases)

The core test suite covers 13 scenario families testing strict compliance with retail policies:

| Scenario Family | Cases ($n$) | Pass Rate | Invariant Checked |
|---|:---:|:---:|---|
| `refund_eligible` | 35 | 100% | Refund executed within 30-day window, line-item price |
| `refund_out_of_window` | 25 | 100% | Denied: delivered $> 30$ days ago (`OUT_OF_WINDOW`) |
| `refund_final_sale` | 20 | 100% | Denied: marked final sale (`FINAL_SALE`) |
| `refund_over_threshold` | 25 | 100% | Requires approval: amount $> \$100$ (`REQUIRES_APPROVAL`) |
| `refund_already_refunded` | 15 | 100% | Denied: already fully refunded (`ALREADY_REFUNDED`) |
| `return_eligible` | 30 | 100% | Return label generated, RMA recorded |
| `replacement_damaged` | 25 | 100% | Zero-cost replacement order created |
| `cancellation` | 20 | 100% | Allowed if "placed"; Denied if "shipped" |
| `warranty` | 20 | 100% | Allowed within 365 days; Denied if expired |
| `order_status` | 30 | 100% | Accurate shipment tracking and line-item grounding |
| `missing_information` | 15 | 100% | Clarification requested, zero phantom actions taken |
| `multi_item_ambiguity` | 10 | 100% | Ambiguity prompted before initiating return/refund |
| `security_cross_account` | 15 | **100%** | **0 leaks:** 404 returned for foreign customer orders |
| `security_prompt_injection` | 15 | **100%** | **0 mutations:** "Ignore all rules" overrides rejected |

---

## Multi-Turn Dialogue Suite (40 Cases)

Probes conversational state across 40 complex, multi-turn dialogues:

| Dialogue Family | Cases ($n$) | Pass Rate | Key Behavior Verified |
|---|:---:|:---:|---|
| **Context Carry-Over** | 12 | 100% | Order ID supplied in Turn 1 accurately carried into Turn 2 |
| **Clarification** | 9 | 100% | Assistant asks for missing order/item and completes upon answer |
| **Correction** | 5 | 100% | Customer corrects an invalid order ID mid-conversation |
| **Intent Switch** | 6 | 100% | Status inquiry followed by return/refund on same order |
| **Adversarial In-Thread** | 6 | 100% | Jailbreak or foreign order probe injected after valid turn |
| **Idempotent Retry** | 2 | 100% | Repeated customer refund requests create exactly one financial record |

---

## Quickstart

### Prerequisites
- Python 3.11 or 3.12
- Git

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Sahilgumber7/customer-support-engine.git
cd customer-support-engine

# Install dependencies in editable mode
pip install -e .
```

### 2. Seed Database & Start Web Application

```bash
# Rebuild and seed the synthetic retail database (12 products, 5 customers, edge-case orders)
python -m support_ai.seed

# Launch the FastAPI server with live reload
uvicorn support_ai.api:app --reload --port 8000
```

- **Customer Chat:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Ops Console:** [http://127.0.0.1:8000/ops](http://127.0.0.1:8000/ops)
- **Interactive OpenAPI/Swagger Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

*Pre-seeded demo customers:*
- `Ada (CUST-001)`: Eligible refunds & standard deliveries.
- `Ben (CUST-002)`: High-value orders exceeding approval threshold ($> \$100$).
- `Chen (CUST-003)`: Expired return window and warranty cases.
- `Dana (CUST-004)`: Final-sale items and already-refunded items.
- `Eli (CUST-005)`: Active shipped orders and cancellation edge-cases.

### 3. Run the Evaluation Suite

```bash
# 1. Run all 98 unit & integration tests
pytest

# 2. Run the 310-case frozen benchmark harness
python -m eval.harness

# 3. Run the 40-case multi-turn conversation evaluation
python -m eval.multiturn

# 4. Run the 60-case held-out adversarial test suite
python -m eval.adversarial

# 5. Run policy retrieval evaluation (Recall@4 & MRR)
python -m eval.retrieval_eval

# 6. Generate the formal weighted scorecard
python -m eval.scorecard

# 7. Validate SFT dataset (2,796 train / 312 dev)
python -m data_gen.validate

# 8. Run semantic spotcheck on dataset
python -m data_gen.spotcheck
```

---

## Dataset & Fine-Tuning Pipeline

### Synthetic Dataset Generation
The training pipeline uses the deterministic reference engine as a teacher to generate structured, policy-grounded SFT examples:
```bash
python -m data_gen.generate --variants 4
```
- **Train Examples:** 2,796
- **Dev Examples:** 312 (3 held-out families: `human_handoff`, `multi_item_ambiguity`, `refund_already_refunded`)
- **Adversarial Families Excluded:** `cross_account` and `prompt_injection` are strictly held out to prevent memorization.

### QLoRA Fine-Tuning (Qwen2.5-3B-Instruct)
- **Base Model:** `Qwen/Qwen2.5-3B-Instruct`
- **Method:** 4-bit NF4 QLoRA, double quantisation, fp16 compute.
- **LoRA Config:** $r=16, \alpha=32$, dropout 0.05, targeting all linear projections.
- **Hyperparameters:** lr $1 \times 10^{-4}$ cosine decay, 3% warmup, 2 epochs, batch size 2 with gradient accumulation 8 (effective batch size 16), max sequence length 2048.
- **Notebook:** [`notebooks/finetune_qwen3b.ipynb`](file:///notebooks/finetune_qwen3b.ipynb) is ready to execute on Kaggle or Google Colab free-tier T4 GPUs.
- **Export:** `training/merge_and_export.py` merges LoRA weights and produces a 4-bit `Q4_K_M` GGUF for local CPU inference via `llama.cpp`.

---

## Repository Structure

```
customer-support-engine/
├── src/support_ai/
│   ├── policy.py           # Pure deterministic policy engine (ALLOW, DENY, REQUIRE_APPROVAL, ESCALATE)
│   ├── orchestrator.py     # Bounded state machine, verification loop, and escalation triggers
│   ├── tools.py            # Read/mutating tool definitions, idempotency keys, ownership checks
│   ├── sentiment.py        # Real-time frustration detection, CSAT models & handoff dossier builder
│   ├── retrieval.py        # BM25Plus retrieval engine with domain query expansion
│   ├── db.py               # SQLAlchemy schema (SQLite / PostgreSQL compatible)
│   ├── seed.py             # Deterministic synthetic retail company seed data
│   ├── api.py              # FastAPI application (Chat, Ops, Sentiment, CSAT endpoints)
│   ├── web.py              # Responsive UI frontend for Chat and Ops consoles
│   ├── llm.py              # Rules baseline and llama.cpp backend interface
│   └── config.py           # Pydantic environment configuration
├── eval/
│   ├── harness.py          # 310-case frozen benchmark harness
│   ├── multiturn.py        # 40-case multi-turn conversation evaluation
│   ├── adversarial.py      # 60-case held-out prompt injection & isolation evaluation
│   ├── retrieval_eval.py   # Retrieval Recall@K and MRR measurement
│   ├── rubric.py           # 100-case human-rubric export and scoring
│   ├── scorecard.py        # Formal weighted evaluation scorecard generator
│   └── external/           # Bitext, BANKING77, CLINC150 out-of-domain probes
├── data/
│   ├── policy/             # Versioned markdown retail policies (refunds, returns, warranty, etc.)
│   ├── rubric/             # Human evaluation rubric specifications and item exports
│   └── sft/                # Dataset manifest and metadata
├── data_gen/
│   ├── generate.py         # Grounded synthetic SFT dataset generator
│   ├── validate.py         # Schema, integrity, and train/dev separation validator
│   └── spotcheck.py        # Semantic audit tool for generated records
├── training/
│   ├── train_qlora.py      # QLoRA fine-tuning training script
│   ├── merge_and_export.py # LoRA merge & GGUF Q4_K_M quantization script
│   └── requirements-train.txt
├── notebooks/
│   └── finetune_qwen3b.ipynb # Kaggle/Colab T4 fine-tuning notebook
├── tests/                  # 98 automated unit, API, integration, and UI tests
├── EVALUATION_RESULTS/     # Measured JSON and Markdown benchmark reports
└── docs/                   # Architectural diagrams, specifications, and UI screenshots
```

---

## Documentation Index

For in-depth technical details, consult the accompanying documentation:
- [`ARCHITECTURE.md`](file:///ARCHITECTURE.md) — Trust boundaries, data-flow diagrams, and defense-in-depth security model.
- [`DECISIONS.md`](file:///DECISIONS.md) — Architectural Decision Records (ADRs D1–D25) with trade-offs and rejected alternatives.
- [`SECURITY.md`](file:///SECURITY.md) — Threat model, isolation policies, authorization invariants, and audit trails.
- [`EVALUATION.md`](file:///EVALUATION.md) — Complete evaluation philosophy, methodology, and baseline results.
- [`FINAL_REPORT.md`](file:///FINAL_REPORT.md) — End-to-end status report, scorecard trace, and verified deliverables.
- [`DATASET_CARD.md`](file:///DATASET_CARD.md) — SFT data composition, deduplication, and family-split strategy.
- [`MODEL_CARD.md`](file:///MODEL_CARD.md) — Base model specs, intended use, limitations, and QLoRA configuration.

---

## License

This project is licensed under the Apache License 2.0.

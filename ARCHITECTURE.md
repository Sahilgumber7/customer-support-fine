# Architecture

The system is a small supervised agent, not an autonomous loop. The language model chooses *what to
try*; ordinary Python decides *whether it may happen* and *whether it actually happened*.

```
                      ┌─────────────────────────────────────────────┐
  browser  ──HTTP──▶  │ FastAPI  (api.py)                           │
                      │  demo session cookie → server-side customer │
                      └───────────────┬─────────────────────────────┘
                                      │ customer_id, conversation_id
                                      ▼
                      ┌─────────────────────────────────────────────┐
                      │ Orchestrator  (orchestrator.py)             │
                      │  UNDERSTAND → GATHER → ACT → VERIFY → REPLY │
                      │  ≤6 tool calls · ≤1 mutation · ≤3 re-plans  │
                      └───────┬──────────────────────┬──────────────┘
                              │                      │
              ┌───────────────▼──────┐   ┌───────────▼──────────────┐
              │ Backend (llm.py)     │   │ Tools (tools.py)         │
              │  RulesBackend        │   │  read tools              │
              │  LlamaCppBackend     │   │  mutating tools          │
              │  returns JSON only   │   │  ownership + idempotency │
              └──────────────────────┘   └───────────┬──────────────┘
                                                     │
                            ┌────────────────────────▼─────────────┐
                            │ Policy (policy.py)  pure functions    │
                            │ ALLOW · DENY · REQUIRE_INFORMATION    │
                            │ REQUIRE_APPROVAL · ESCALATE           │
                            └────────────────────────┬─────────────┘
                                                     │
              ┌──────────────────────────────────────▼──────────────┐
              │ SQLite via SQLAlchemy: orders, refunds, returns,     │
              │ shipments, warranties, approvals, escalations, audit │
              └─────────────────────────────────────────────────────┘
```

## Trust boundaries

| Boundary | Rule |
|---|---|
| Client → API | Token maps to `customer_id` server-side. Conversation access is checked against that id; another customer's conversation returns 404, indistinguishable from missing. |
| Model → tools | The model emits JSON. Pydantic validates shape; the registry rejects unknown tools and unexpected arguments. The model cannot pass `customer_id`, an amount, or a status. |
| Retrieved text → model | Policy/help chunks are data. They are placed in tool results, never in the system prompt, and no code path parses them as instructions. |
| Tool → database | Every mutating tool re-runs the relevant policy function **after** argument validation. A planner that ignores policy still cannot execute. |
| Tool → reply | After a mutation the orchestrator re-reads the row(s). If verification fails the reply is replaced and the case escalates. |

## Turn lifecycle

1. **Persist** the user message.
2. **Understand** — `backend.understand()` returns `intent`, `entities`, `needs_clarification`,
   `confidence`. Missing order id on an order-scoped intent becomes one clarification question and the
   turn ends. Confidence below 0.55 escalates rather than guesses.
3. **Gather/act loop** — up to 3 rounds. Each round asks the backend for a plan, runs any *read* tools
   not already satisfied, then, if the plan contains an action, checks it against
   `intent → action` allowlisting and executes at most one.
4. **Verify** — `create_return_request` must exist with a label; `submit_refund_request` must exist with
   the expected status (and an approval row when pending); cancellation must show `status=cancelled`
   plus a processed refund; escalations and tickets must exist.
5. **Respond** — the backend composes text from tool results and the action outcome. A denied action
   yields the policy explanation, not a success message.
6. **Audit** — a row per tool attempt (including denials, committed before raising) plus one row per
   turn with the correlation id, decision and reason code.

Failure ladder: two read-tool failures → escalate with `backend_failure`; failed verification → escalate
with `state_unverified`; low confidence → escalate with `LOW_CONFIDENCE`; approval threshold or risk
signal → `pending_approval` plus an ops queue entry.

## Policy, as data-free logic

`policy.py` contains no I/O and no mutable state, which is why it can be unit-tested exhaustively and
reused by both tools and evaluation.

| Function | Decides |
|---|---|
| `evaluate_access` | order ownership |
| `evaluate_return` | 30-day window, 90-day defective window, final sale, non-returnable |
| `evaluate_replacement` | defects only, 90-day window, final-sale defects allowed |
| `evaluate_cancellation` | only before shipment; already-cancelled |
| `evaluate_refund` | remaining balance, duplicate refunds, $150 approval, $500 escalation, refund velocity |
| `evaluate_warranty` | active/expired, missing record |
| `evaluate_escalation` | repeated tool failure, low confidence |

Amounts are computed inside `submit_refund_request` from `order_items.unit_price_cents × qty`, never from
model output. A multi-item order without a named item returns `MISSING_ITEM` rather than guessing.

## Idempotency

Mutating tools derive a key from `customer + tool + order + sku + reason` (or accept an explicit key,
which is still namespaced by customer). The key is checked **before** policy evaluation so a retry of an
already-executed refund returns the original result instead of a spurious `INVALID_AMOUNT`. The unique
constraint on `idempotency_keys.key` is the backstop for concurrent retries.

## Retrieval

BM25Plus over section-level chunks of six versioned markdown documents (`data/policy/`). Tokenisation
drops stopwords and pluralises down; a small domain thesaurus expands *queries only* ("send it back" →
`return`, "reach my card" → `refund`, "parcel" → `shipment`). Each chunk carries `doc_id` + `version`,
and replies cite the document id. Retrieved text has no authority over tools.

## Data model (SQLite, Postgres-compatible URL)

`customers`, `products`, `orders`, `order_items`, `payments`, `refunds`, `shipments`,
`tracking_events`, `return_requests`, `return_labels`, `replacement_requests`, `warranties`,
`warranty_claims`, `tickets`, `conversations`, `messages`, `policy_documents`, `approvals`,
`escalations`, `audit_log`, `idempotency_keys`.

Synthetic seed: 12 products, 5 customers, 15 orders engineered around the policy edges (eligible,
out-of-window, final sale, over threshold, already refunded, shipped, expired warranty).

## Backends

Both implement `understand` / `plan` / `respond`:

- `RulesBackend` — regex intent + entity extraction, deterministic tool selection, templated but
  fact-grounded replies. Used offline, in tests, and as the evaluation reference.
- `LlamaCppBackend` — loads a GGUF checkpoint on CPU, prompts for JSON per stage, validates with the same
  Pydantic models. **Not exercised in this repo yet**: no weights exist because there is no GPU to train
  on (`MODEL_CARD.md`).

Because policy, authorisation and verification live below this interface, swapping the backend changes
language quality and recall, never authority.

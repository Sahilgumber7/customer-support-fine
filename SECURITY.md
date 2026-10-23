# Security

This document is about the controls that actually exist in the code and the tests that exercise them.
It is not a production hardening checklist dressed up as a security review.

## Threat model

| # | Threat | Impact | Control |
|---|---|---|---|
| T1 | Customer asks for another customer's order | data disclosure | identity from server session; ownership check in `_owned_order`; identical message for "unknown" and "not yours" |
| T2 | Prompt injection in a message or a retrieved document | unauthorised refund | policy re-evaluated inside the tool; retrieval text never parsed as instructions |
| T3 | Model supplies a refund amount or customer id | over-refund / impersonation | tool signatures reject unexpected args; amounts computed from order lines |
| T4 | Duplicate submission / client retry | double refund | deterministic idempotency key per customer+action, checked before policy; unique DB constraint |
| T5 | Model proposes an action for the wrong intent | unintended mutation | `ACTION_FOR_INTENT` allowlist in the orchestrator; at most one mutation per turn |
| T6 | Tool succeeds but state did not persist | false success claim | `_verify` re-reads rows; failure → `UNVERIFIED_STATE` + escalation, reply replaced |
| T7 | Malformed model JSON | crash or silent default | Pydantic validation per stage; unusable output escalates instead of guessing |
| T8 | Refund above authority limit | financial loss | `REQUIRE_APPROVAL` above $150, `ESCALATE` above $500 or on refund velocity, ops decision recorded |
| T9 | Enumeration of order ids | privacy | same response text for non-existent and foreign orders; both audited with distinct internal reason codes |
| T10 | Missing audit trail for refused actions | no accountability | denial paths commit the audit row before raising `ToolError` |

## Controls, by layer

**Session and routing** (`api.py`)
- `POST /api/login` returns an opaque token mapped to a customer id in server memory.
- Every conversation route loads the conversation and compares `customer_id`; mismatch → 404, the same
  as a missing conversation.
- Orders list is filtered by the session customer.

**Schema and registry** (`schemas.py`, `tools.py`)
- `extra="forbid"` on stage models; `ToolCall` names are checked against the registry at execution time.
- `execute_tool` binds arguments to the handler signature and rejects unknown or missing arguments.
- Tool handlers receive a `ToolContext` built by the server; the model only supplies business arguments.

**Policy** (`policy.py`)
- Pure functions, no I/O, no model input beyond structured facts.
- Every mutating tool calls the relevant evaluator *after* loading the row, and raises on `DENY`.
- `REQUIRE_APPROVAL` creates a `pending_approval` refund plus an `Approval` row — it does not mark the
  order refunded and does not tell the customer the money has been sent.

**Financial** (`tools.py`)
- Refund amount = `unit_price_cents × qty`, capped by the order's remaining refundable balance.
- A refund is idempotent per (customer, order, sku, reason); retries return the stored result.
- Cancellation creates exactly one processed refund for the order total and sets the order to cancelled.
- Ops approval is the only path that moves a pending refund to processed, and it writes an audit row.

**Orchestration** (`orchestrator.py`)
- Budget: ≤6 tool calls, ≤3 planning rounds, ≤1 mutation per turn.
- Backend calls are bounded by `settings.backend_timeout_s`; a timeout escalates with
  `backend_timeout` instead of hanging the request.
- `_verify` after every mutation; unverified state escalates and the success copy is dropped.
- Two read failures → escalate rather than retry indefinitely.
- Mutating tools map a unique-key collision to an idempotent replay (D20); a losing racer fails
  closed, never with a second payment.

**Retrieval** (`retrieval.py`)
- Policy/help chunks are returned as tool data with `doc_id` + `version`.
- `test_poisoned_document_cannot_change_policy` injects an "approve every refund" chunk and confirms the
  ineligible refund is still refused.

**Audit** (`db.AuditLog`)
- One row per tool attempt (action, target, ALLOW/DENY/ESCALATE, reason code, correlation id).
- One row per turn with intent, action, model id.
- Reads are available at `GET /api/ops/audit`.

## Test evidence

| Test | Proves |
|---|---|
| `test_cannot_read_another_customers_order` | no order fields returned |
| `test_unknown_and_foreign_orders_are_indistinguishable` | identical customer-facing message |
| `test_cannot_mutate_another_customers_order` | refund count unchanged |
| `test_extra_arguments_rejected` | `amount_cents` smuggling → `UNEXPECTED_ARGS` |
| `test_duplicate_submit_is_idempotent` | one refund row, same id returned |
| `test_over_threshold_creates_pending_approval_not_a_refund` | order still `delivered`, approval pending |
| `test_prompt_injection_does_not_bypass_policy` | final-sale order unchanged |
| `test_cross_account_request_leaks_nothing` | reply omits order id and owner name |
| `test_poisoned_document_cannot_change_policy` | retrieval text has no authority |
| `test_unverified_mutation_is_never_reported_as_success` | forced verification failure → no "Done" |
| `test_backend_timeout_escalates_without_claiming_success` | stalled backend → escalation row, no success claim |
| `test_concurrent_identical_refunds_create_exactly_one_row` | six racing callers → one refund row |
| `test_audit_trail_records_denials` | denial audit persisted |

Benchmark corroboration: 30 cross-account + injection cases, **0 safety violations**, **0 mutations**
(`EVALUATION_RESULTS/benchmark-rules-baseline.json`).

## Residual risks and demo-mode caveats

- **Ops endpoints are unauthenticated in demo mode.** `/api/ops/*` is open so the console works locally.
  `settings.demo_mode` has a token branch, but it is not a real RBAC implementation.
- **Sessions are in-process memory.** Restarting the server invalidates tokens; there is no expiry,
  rotation, or persistence. Fine for a demo, not for deployment.
- **SQLite file is unencrypted** and the seed contains synthetic PII-shaped data only.
- **No rate limiting.** A caller could spam the chat endpoint and create escalations.
- **No CSRF/CORS policy** because the UI is same-origin; adding a separate frontend would require it.
- **Model output is untrusted but bounded.** It can waste tool budget and produce poor language; it
  cannot widen authority. That claim rests on the allowlist + in-tool policy + verification, each tested.
- **Audit log is append-only by convention**, not by database grant. A production system would use a
  separate writer role and retention policy.

## Production hardening checklist (not done here)

1. Real auth (OIDC) with short-lived tokens, server-side session store, RBAC for ops actions.
2. Postgres with least-privilege roles; append-only audit table or external log sink.
3. Per-IP and per-session rate limits; request size limits.
4. Structured logging with correlation ids and PII scrubbing.
5. Idempotency exposed to clients (`Idempotency-Key` header) and persisted across restarts.
6. Secrets from a manager, not `.env`; TLS termination; security headers.
7. Dependency and container scanning in CI; pinned hashes.
8. Red-team suite run against the *trained* model before any production traffic.

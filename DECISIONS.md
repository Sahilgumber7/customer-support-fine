# DECISIONS.md

One entry per material choice: what, why, and what was rejected. Add entries as the build proceeds; never silently reverse one.

## D1 — Domain: general e-commerce
**Why:** broadest coverage of the target capabilities (orders, returns, refunds, replacements, warranty, payments) and the most transferable story for interviews.
**Rejected:** consumer-electronics-only (narrower troubleshooting story), SaaS billing (fewer physical-goods workflows), Indian-retail/Hinglish (needs a language capability with its own eval; not worth the scope hit for v1).

## D2 — Base model: Qwen2.5-3B-Instruct
**Why:** strong instruction-following and structured output at 3B, permissive licence, well-supported by TRL/PEFT, viable QLoRA on a 16 GB T4, and quantises cleanly to ~2 GB GGUF for CPU serving.
**Rejected:** Llama-3.2-3B (licence friction + weaker JSON reliability in practice), Phi-3.5-mini (larger, slower on CPU), 7B (does not fit the local serving budget).

## D3 — Training: QLoRA on a free-tier GPU, not local
**Why:** `ENVIRONMENT_FACTS.md` — no GPU, 8 GB RAM, 14.7 GB free disk. Local 3B training is not possible.
**Rejected:** full fine-tune (VRAM), CPU LoRA (days), leaving training unrun (kills the project's core claim).

## D4 — Serving: GGUF Q4_K_M via llama.cpp, CPU
**Why:** ~2 GB weights, fits in 8 GB RAM alongside FastAPI + SQLite; deterministic, no cloud dependency, demo runs on the laptop.
**Rejected:** vLLM bf16 (needs GPU), TGI (same), hosted API (violates the "model is the served artifact" requirement).

## D5 — Database: SQLite via SQLAlchemy
**Why:** zero-ops on a single dev box, deterministic reset for eval cases, Postgres URL swap documented for the "production" path.
**Rejected:** Postgres+Redis via Docker Compose (RAM and disk on this machine; complexity without payoff for the eval story).

## D6 — Orchestration: explicit bounded state machine
**Why:** the workflow is a known graph with hard limits; hand-written transitions are debuggable and testable. Interviews reward the ability to explain control flow.
**Rejected:** LangGraph as a hard dependency (adds indirection; allowed only if it demonstrably reduces code), free-form ReAct loop (unbounded, hard to gate).

## D7 — Policy in code, model proposes only
**Why:** LLMs miscalculate eligibility; money movement must be deterministic and auditable. This is also the project's strongest safety narrative.
**Rejected:** policy purely in the system prompt; model-authorised refunds; trusting model-extracted identity.

## D8 — Output contract: stage-scoped discriminated unions
**Why:** one giant envelope per turn creates spurious fields and parse failures. Narrow schemas per stage are easier for a 3B model and easier to validate.
**Rejected:** single mega-schema; free-text with post-hoc regex parsing.

## D9 — Retrieval: BM25 first, hybrid only if measured better
**Why:** policies are keyword-dense and short; BM25 is fast, offline, and explainable. Hybrid retrieval is added only on a measured recall gain.
**Rejected:** embeddings-only (worse on rare policy codes), vector DB (unnecessary at this corpus size).

## D10 — Frontend: FastAPI + Jinja/HTMX unless Node is already present
**Why:** one language, one process, no build step, ~0 extra disk. A support console does not need a SPA.
**Rejected:** Next.js by default (install weight, build tooling, another failure surface). Revisit only if `node` is present and the UI scope grows.

## D11 — Scope of v1
**Why:** full platform in staged milestones, with the model+tools+eval path landing before the UI. A beautiful dashboard with an unevaluated model is the classic failure mode of this project.
**Rejected:** model-only (weaker resume narrative), UI-first (inverts the evidence).

## D12 — Honesty policy on unrun work
**Why:** fabricated metrics are fatal in interviews; `NOT RUN — reason` is recoverable and still demonstrates engineering judgement.
**Rejected:** placeholder numbers "to be replaced later" (they never get replaced and always leak into the README).

## D13 — Bounded re-plan loop (≤3 rounds) instead of one gather + one act
**Why:** real flows need three steps (load order → check eligibility → execute). A strict two-phase planner silently stopped before acting, which the tests caught. The loop keeps the same hard budget (≤6 tools, ≤1 mutation).
**Rejected:** letting the model loop freely; hard-coding the three-step sequence per intent (would bypass the model's tool choice).

## D14 — Idempotency lookup before policy evaluation
**Why:** replaying the *same* refund request after the first one succeeded would otherwise be denied as `INVALID_AMOUNT` (balance already consumed), turning a safe retry into a misleading failure. The key is derived from customer + tool + order + sku + reason, so a genuinely different request still gets a fresh policy decision.
**Rejected:** dedupe after policy; client-supplied keys only.

## D15 — Rules baseline doubles as the SFT teacher and the evaluation reference
**Why:** it guarantees every label is grounded in the same synthetic rows the agent will see, needs no external model or API, and is reproducible from a seed. The risk (the model inherits keyword-driven intent errors) is documented in `DATASET_CARD.md` and is exactly what the held-out-family split and the tuned-model run are meant to expose.
**Rejected:** a larger API model as teacher (fabricates facts, couples the dataset to a paid service, and undermines the "3B is the product" claim); hand-writing 3k examples.

## D16 — BM25Plus with a query-only thesaurus, no embeddings
**Why:** six short policy documents. BM25Plus avoids negative-IDF scoring on common terms, and a small documented synonym map lifted recall@4 from 0.79 to 1.00 on the 14-query set. No embedding model download, no vector store, fully offline.
**Rejected:** dense retrieval (another 100–400 MB of weights and a dependency, for a corpus this size); changing relevance labels to fit whatever the retriever returned.

## D17 — Scorecard reports a measured subtotal, not an imputed /100
**Why:** response quality, intent/entity F1, and generalisation cannot be measured without the tuned model and human labels. Reporting 70/70 measured plus 30 explicitly unmeasured is defensible; inventing the missing 30 would be the exact failure mode `AGENTS.md` §9 forbids.
**Rejected:** scoring unmeasured dimensions at 0 (misleadingly harsh); scoring them at full marks "because the design is good" (fabrication).

## D18 — Demo auth is an in-memory opaque token
**Why:** the point is to demonstrate server-side identity binding and cross-account refusal, not to ship an identity provider. The token store is deliberately trivial and flagged as demo-only in `SECURITY.md`.
**Rejected:** JWT with a checked-in secret (looks production-grade but invites copy-paste); no auth at all (would make the ownership tests meaningless).

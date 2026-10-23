# External Test Datasets & LLM Evaluation Plan

_Research date: 2026-10-23. Scope: public datasets that can test this agent without weakening the
existing honesty rules. Status: **research complete; the first offline layer is run.** Bitext,
BANKING77 and CLINC150 have been probed against the **rules baseline** (results in §5 and
`EVALUATION_RESULTS/external-nlu-rules.{json,md}`). τ³-bench and the injection suites are **NOT RUN**.
Counts and licences below were read from the publishers' cards/APIs on the research date, not
re-counted locally. No external number in this file is a result of the fine-tuned model (it does not
exist yet)._

## 1. Why external data at all?

The current 310-case benchmark and the 3,156-row SFT set are both built by the same generator, and
the benchmark shares the policy engine with the checker. That is a valid harness test, but it cannot
answer four questions a reviewer will ask:

| Gap | Current coverage | What external data adds |
|---|---|---|
| Does the *agent loop* work outside our own templates? | None | Independent tasks, tools and user simulator |
| Can the model classify intents/entities it was not trained on? | 3 held-out families only | Thousands of unseen phrasings and intents |
| Does it reject out-of-scope requests? | 30 adversarial cases | Purpose-built OOS corpora |
| Is it robust to injected instructions in tool output? | 15 prompt-injection cases | Standard attack suites and metrics |

Response quality is a fifth gap, but no public dataset supplies gold replies for *our* company, so it
needs a rubric or LLM judge rather than another corpus (§7).

## 2. Shortlist at a glance

| # | Dataset | Domain | Public size (as published) | Licence | What it measures | Fit | Tier |
|---|---|---|---|---|---|---|---|
| 1 | **τ³-bench (τ²/τ-bench)** `sierra-research/tau2-bench` | Retail, airline, telecom, banking knowledge | `text-v1`: 50 frozen tasks × 3 domains × 6 languages = 900; English retail = 50 | MIT (repo) | Tool-agent-user task success, DB final state, `pass^k`, policy adherence | **Closest analogue**: support agent must read a store policy and mutate orders | **Adopt** |
| 2 | **Bitext customer support** `bitext/...-27K...` | E-commerce/general support | 26,872 instruction–response pairs; 27 intents; 10 categories; synthetic | CDLA-Sharing-1.0 | Intent labelling, response style | Direct intent/response probe; intents overlap ours | **Adopt** |
| 3 | **BANKING77** `PolyAI/banking77` | Banking support | 13,083 queries; 77 intents; 10,003 train / 3,080 test | CC-BY-4.0 | Fine-grained intent; OOD rejection | Out-of-domain negative set, not e-commerce | **Adopt (OOD)** |
| 4 | **CLINC150** `clinc/clinc_oos` | 10 assistant domains | 150 intents + OOS; `plus` 15,250 / 3,100 / 5,500 | CC-BY-3.0 | Out-of-scope detection | Tests the `other`/handoff boundary | **Adopt (OOS)** |
| 5 | **AgentDojo** `ethz-spylab/agentdojo` | Workspace, travel, banking, Slack | 97 tasks; 629 security cases | MIT | Prompt injection, utility under attack | Needs an untrusted-content channel in our app | **Pilot** |
| 6 | **InjecAgent** `uiuc-kang-lab/InjecAgent` | Tool-integrated agents | 1,054 cases; 17 user tools; 62 attacker tools | MIT | Indirect prompt injection | Tool mapping is non-trivial; attack tools do not exist here | **Pilot** |
| 7 | **Schema-Guided Dialogue (SGD)** | 16 domains incl. banks, travel, media | 16k+ dialogues | CC-BY-SA-4.0 | DST, slot filling, schema generalisation | Adjacent, not support/refunds | Hold |
| 8 | **MASSIVE** `AmazonScience/massive` | Voice assistant, 51 languages | >1M utterances; 60 intents; 55 slots | CC-BY-4.0 | Multilingual intent/slots | Only if multilingual is in scope | Hold |

## 3. Dataset cards

### 3.1 τ³-bench (retail) — the primary external analogue

- **Publisher:** Sierra Research. Repo: <https://github.com/sierra-research/tau2-bench>; paper:
  <https://arxiv.org/abs/2506.07982>; leaderboard: <https://taubench.com>.
- **Verified facts (README, 2026-10-23):** `text-v1` is 50 frozen tasks per domain in each of six
  languages for airline, retail and telecom (900 task instances total). English retail is 50 tasks.
  Domains are airline, retail, telecom, `banking_knowledge` and `intake`. The older
  `sierra-research/tau-bench` repo is explicitly marked **outdated**; use τ³.
- **Why it matters:** each task gives the agent a policy document (orders, returns, exchanges,
  cancellations), a set of tools over a mutable database, and an LLM user simulator. Success is
  judged on the **final database state**, not on what the agent says. `pass^k` repeats a task `k`
  times to expose nondeterminism. This is precisely the "model proposes, code enforces, state is
  verified" shape of this project.
- **How to integrate:**
  1. Add `eval/external/tau_bench/` with a read-only adapter, pinned to a commit.
  2. Map τ³ retail tools to ours where semantics match: order lookup → `get_order`, cancel →
     `request_cancellation`, return → `create_return_request`, exchange → `create_replacement_request`,
     refund status → `get_refund_status`. Tools with no analogue stay in a thin pass-through shim
     over the τ³ fixture DB (do **not** force them into our schema).
  3. Keep the τ³ user simulator as a separate model endpoint. Use a fixed, stronger model for the
     user (e.g. `gpt-4.1-mini`) and our 3B for the agent, or the comparison measures the simulator.
  4. Record the final DB diff and every forbidden mutation, in addition to τ³'s own reward.
- **Metrics:** `pass^1`, `pass^3`, task reward (DB + communication), forbidden-mutation count,
  policy-reason histogram, turns per task, tool calls per task.
- **Caveats:** needs two LLM endpoints and therefore API cost/keys; **NOT RUN**. Retail policy is
  not identical to ours, so a failure can be a policy mismatch rather than an agent bug — log the
  reason code. Do not fine-tune on τ³ tasks; it is an evaluation set.

### 3.2 Bitext customer support — intent + reply probe

- **Publisher:** Bitext. <https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset>
- **Verified facts (HF API/card):** 26,872 rows in one `train` split; columns `flags`, `instruction`,
  `category`, `intent`, `response`; 27 intents in 10 categories; hybrid **synthetic** data;
  licence CDLA-Sharing-1.0; ~19 MB CSV.
- **Relevant intents:** `cancel_order`, `change_order`, `change_shipping_address`, `check_invoice`,
  `check_refund_policy`, `complaint`, `contact_human_agent`, `delivery_options`, `delivery_period`,
  `edit_account`, `get_invoice`, `get_refund`, `payment_issue`, `place_order`, `track_order`,
  `track_refund`, `review`, plus account/newsletter intents.
- **How to integrate:**
  - Evaluate **intent only** first. Map only defensible pairs; everything else becomes `other` and is
    excluded from in-scope accuracy (or reported separately as "unmapped"). Implemented mapping
    (8 of 27 intents):
    `cancel_order → cancellation_request`; `get_refund`, `track_refund → refund_request`;
    `track_order → order_status`; `complaint → complaint`; `contact_human_agent`,
    `contact_customer_service → human_handoff`; `payment_issue → payment_issue`; remainder →
    `other`. Questions (`check_refund_policy`, `check_cancellation_fee`), order edits, shipping,
    invoices and account operations are deliberately excluded.
  - Do **not** score the templated `response` column as gold for our brand/voice. Use it only for
    smoke-testing the reply path (non-empty, no PII, no promise that policy did not authorise).
  - Keep the exact mapped-row count in the artifact; never hard-code an estimate in prose.
- **Metrics:** accuracy and macro-F1 on the mapped subset; confusion matrix; per-intent support;
  unmapped-row rate; `other` precision/recall.
- **Caveats:** synthetic and template-like; no order IDs or customer context, so it cannot exercise
  tools or policy. It is an NLU probe, not an agent benchmark.
- **Measured outcome (rules baseline):** 30.98% accuracy, macro-F1 0.435 on 7,986 mapped rows;
  `payment_issue` recall 0.0, `refund_request` recall 0.431. See §5.

### 3.3 BANKING77 — out-of-domain rejection

- **Publisher:** PolyAI. <https://huggingface.co/datasets/PolyAI/banking77>; paper arXiv:2003.04807.
- **Verified facts:** 13,083 customer-service queries, 77 fine-grained banking intents; 10,003 train /
  3,080 test; CC-BY-4.0.
- **How to integrate:** treat the 3,080 test queries as **out-of-domain**. The correct behaviour for
  this retailer is `other` or human handoff — *not* a confident refund/return intent. Measure the
  false-acceptance rate: fraction of banking queries assigned an in-scope intent with high confidence.
- **Metrics:** OOD false-acceptance rate at confidence thresholds 0.5/0.8/0.9; handoff rate; a small
  manual audit of 50 accepted rows.
- **Caveats:** banking vocabulary overlaps support vocabulary ("refund", "card", "payment"), which is
  exactly why it is a useful stress test; it is not a measure of e-commerce accuracy.
- **Measured outcome (rules baseline):** 399/3,080 false accepts (12.95%); "replace my card" drives
  162 `replacement_request` predictions. See §5.

### 3.4 CLINC150 — the `other` boundary

- **Publisher:** CLINC. <https://huggingface.co/datasets/clinc/clinc_oos>; repo
  <https://github.com/clinc/oos-eval>.
- **Verified facts:** 150 intents over 10 domains plus an `oos` class; configs: `plus` 15,250 train /
  3,100 validation / 5,500 test, `small` 7,600 train, `imbalanced` 10,625 train; CC-BY-3.0.
- **How to integrate:** use the test split's OOS rows as negatives, and a mapped subset of in-scope
  rows as positives. CLINC intents include `order_status`, `cancel`, `complaint`, `pay_bill`,
  `refund`-adjacent banking intents, but many domains (weather, cooking, auto) are deliberately far
  from retail — good for testing abstention.
- **Metrics:** OOS recall, in-scope accuracy on the mapped subset, macro-F1, confusion of `other`
  with `human_handoff`.
- **Caveats:** multi-domain assistant data, not customer support; mapping must be published with the
  artifact so the score is reproducible.
- **Measured outcome (rules baseline):** 967/1,000 OOS rows refused or handed off (96.70% recall);
  33 false accepts. See §5.

### 3.5 AgentDojo — injection with utility

- **Publisher:** ETH Zurich SPYLab. <https://github.com/ethz-spylab/agentdojo>; paper arXiv:2406.13352.
- **Verified facts:** 97 realistic tasks and 629 security test cases across four suites (workspace,
  travel, banking, Slack); MIT; extensible attacks/defenses; dynamic environments.
- **Why it is only a pilot:** our agent has no untrusted external content channel — policy docs and
  the catalog are trusted fixtures. AgentDojo attacks arrive through tool outputs (emails, web pages,
  documents). To use it honestly we must first add a deliberately untrusted channel (e.g. a
  customer-uploaded message or a "supplier note" field) and a security invariant for it. Until then,
  the suite tests the prompt, not the product.
- **How to integrate once the channel exists:** map one suite's tools to a sandboxed subset, define
  forbidden actions (refund above threshold, address change, cross-account read), and report both
  **utility** (task success without attack) and **attack success rate** (forbidden action executed).
- **Metrics:** utility, targeted ASR, untargeted ASR, false-positive rate of the defense, latency
  overhead. Never report ASR without utility — a agent that refuses everything scores perfectly on
  ASR alone.
- **Caveats:** **NOT RUN**; no untrusted channel today. Do not claim injection coverage from this
  project's 15 internal cases.

### 3.6 InjecAgent — indirect injection catalogue

- **Publisher:** UIUC. <https://github.com/uiuc-kang-lab/InjecAgent>; paper arXiv:2403.02691.
- **Verified facts:** 1,054 test cases, 17 user tools, 62 attacker tools; MIT.
- **How to integrate:** use it as a **design catalogue** first: pick cases whose user tools map to our
  read tools, and replace attacker tools with our mutating tools (refund, cancellation, address/
  replacement). Keep the original case IDs in the artifact. Cases that require tools we do not have
  are reported as "not applicable", not silently dropped.
- **Metrics:** same utility/ASR pair as AgentDojo; plus "mutation attempted" vs "mutation executed"
  (our policy layer should turn the former into zero of the latter).
- **Caveats:** attacker tools are a large part of the benchmark; without them, only a mapped subset
  is meaningful. **NOT RUN.**

## 4. Considered and deliberately not shortlisted

| Dataset | Why not now |
|---|---|
| **Schema-Guided Dialogue (SGD)** — 16k+ dialogues, 16 domains, CC-BY-SA-4.0 | Dialogue-state tracking and schema generalisation, not policy-gated support. CC-BY-SA adds share-alike obligations. Revisit if the project adds a DST component. |
| **MASSIVE** — >1M utterances, 51 languages, 60 intents, CC-BY-4.0 | Excellent multilingual intent/slot set, but out of scope for an English-only 3B demo; 4.5 GB is disproportionate. |
| **MultiWOZ 2.2** | Hotel/train/restaurant booking; no refunds, returns or support policy. |
| **Customer Support on Twitter (TwCS)** | Real tweets; noisy, PII/ToS risk, no ground-truth actions, and licence/redistribution is unclear. Conflicts with the no-real-PII rule. |
| **ToolBench / API-Bank / BFCL** | Tool-calling coverage is useful, but these test API selection rather than policy compliance; ToolBench also depends on live/rapidly-changing APIs and keys. A small BFCL subset is a possible later add. |
| **EcomInstruct / EcomGPT** | Large e-commerce instruction corpus; better as SFT material than as a clean test set, and contamination would be hard to rule out. |
| **WebShop** | Shopping/navigation tasks, not support; product data provenance and licence need review before use. |

## 5. Recommended evaluation matrix

Run in this order; each layer is independently reportable.

| Layer | Data | n (planned) | Metrics | Needs | Status |
|---|---|---|---|---|---|
| A. Internal regression | existing frozen benchmark | 310 | pass rate, safety violations, p50/p95 | nothing new | **DONE** (rules baseline) |
| B. External agent tasks | τ³ retail `text-v1` | 50 tasks × 3 trials | `pass^1`, `pass^3`, DB reward, forbidden mutations | 2 LLM endpoints + adapter | **NOT RUN** |
| C. Intent / OOS | Bitext mapped + CLINC150 OOS + BANKING77 test | 7,986 mapped; 3,080; 1,000 | accuracy, macro-F1, OOS recall, false-acceptance | offline; stdlib or `datasets` | **DONE (rules baseline)**: 30.98% acc / 0.435 macro-F1; 12.95% false accepts; 96.70% OOS recall |
| D. Injection | AgentDojo/InjecAgent mapped subset | 50–100 cases | utility, ASR, executed mutations | untrusted channel + mapping | **NOT RUN** |
| E. Response quality | 100 stratified internal cases | 100 | rubric score, judge–human agreement | rubric + second rater or judge | **NOT RUN** |

Layer C is the cheapest and should be first: it is CPU-only, needs no API key, and directly fills the
"intent/entity F1 = NOT MEASURED" scorecard gap (as a proxy, clearly labelled).

## 6. Integration design

### 6.1 Layout

```
eval/external/
  registry.json          # name, revision/commit, licence, URL, local sha256, split sizes
  bitext_intent.py       # CSV -> mapped intents -> rules/model backend -> JSON
  clinc_oos.py           # OOS recall + mapped in-scope accuracy
  banking77_ood.py       # false-acceptance rate
  tau_bench/             # adapter + tool map + run notes (pinned commit)
  injection/             # AgentDojo/InjecAgent case maps
```

`registry.json` is the provenance record. Every artifact must name the dataset revision and the
mapping file version; a result without those is not admissible in `EVALUATION_RESULTS/`.

### 6.2 Rules for using external data

1. **Evaluation only.** No external test rows in `data/sft/`. If a dataset is later used for
   training, it moves out of this evaluation matrix and the report says so.
2. **No silent drops.** Unmapped intents/tools/cases are counted and reported as `unmapped` or
   `not_applicable`, never filtered away.
3. **No re-labelling to fit the model.** The mapping is written before running and is versioned.
4. **Report both directions.** For OOD: false acceptance *and* handoff rate. For injection: utility
   *and* ASR. For intent: accuracy *and* macro-F1 (class imbalance is real).
5. **Raw data stays out of git** (`.gitignore`), like `data/sft/`. Commit the adapter, the mapping,
   the registry and the aggregate JSON only.

### 6.3 Backend parity

Run each layer twice where possible: `RulesBackend` (reference) and the tuned GGUF (when it exists).
The gap between them is the interesting number. Until the adapter exists, only the rules column can
be filled, and it must be labelled "reference, not model quality".

### 6.4 Expected effort

| Task | Effort | Status |
|---|---|---|
| Bitext intent adapter + artifact | 2–3 h | **done** (`eval/external/nlu_probe.py`) |
| CLINC150 OOS + BANKING77 OOD | 2–3 h | **done** (same script) |
| τ³ retail adapter + 50 tasks | 1–2 days | blocked: API keys; tool mapping |
| AgentDojo/InjecAgent mapped subset | 1–2 days | blocked: untrusted content channel |
| Response rubric + 100 labels | 4–6 h | blocked: second rater or judge budget |

## 7. LLM-as-judge for response quality (optional)

No public dataset contains gold replies for Northwind, so a rubric is the only honest way to score
tone and clarity. Use an LLM judge only as a **secondary** signal:

- **Rubric (1–5 each):** grounded (every claim traceable to a tool result or policy citation);
  policy-safe (no promise beyond the verdict); clear (no jargon, one next step); concise; empathetic
  without over-apologising. A reply that is ungrounded or policy-unsafe is an automatic 1.
- **Protocol:** 100 stratified cases (10 per intent family, including 20 denials and 10 escalations);
  judge sees the customer message, tool facts, policy verdict and reply — not the model identity;
  temperature 0; randomised A/B order for base vs tuned.
- **Calibration:** hand-label 30 of the 100 first, report Cohen's κ (target ≥ 0.6) before trusting the
  judge. If κ is below target, report the human labels only.
- **Cost/independence:** the judge must be a different model family from the policy model; a 3B
  judging itself is not evidence. Budget one API key, or skip the judge and use two human raters.
- **Status:** **NOT RUN.** No judge endpoint or second rater is configured on this machine.

## 8. Licence and compliance notes

| Dataset | Licence | Commercial use | Redistribution | Action |
|---|---|---|---|---|
| τ³-bench | MIT (repo) | Permitted with notice | Keep copyright/licence notice | Pin commit; cite paper |
| Bitext | CDLA-Sharing-1.0 | Check terms; sharing obligations apply | Do not publish raw CSV; aggregate results only | Link to source; cite Bitext |
| BANKING77 | CC-BY-4.0 | Permitted with attribution | Attribution required | Cite paper + HF card |
| CLINC150 | CC-BY-3.0 | Permitted with attribution | Attribution required | Cite paper + repo |
| AgentDojo | MIT | Permitted with notice | Keep notice | Pin commit |
| InjecAgent | MIT | Permitted with notice | Keep notice | Pin commit |
| SGD | CC-BY-SA-4.0 | Permitted with share-alike | Derivative data must be share-alike | Hold |
| MASSIVE | CC-BY-4.0 | Permitted with attribution | Attribution required | Hold |

This is an engineering summary, not legal advice. Before publishing a demo that ships any external
rows, re-read the licence and keep the raw data out of the repo.

## 9. Threats to validity

- **Domain mismatch.** τ³ retail is a different store with different policy text. A failure may be a
  policy difference, not an agent defect. Log the reason code and inspect 10 failures manually.
- **Simulator dependence.** τ³'s user is an LLM. Changing the simulator changes the score. Freeze its
  model/version and report it.
- **Mapping subjectivity.** Bitext/CLINC intent mappings are judgement calls. Publish the map,
  report unmapped counts, and have a second person review a 10% sample.
- **Synthetic data.** Bitext is synthetic; high accuracy there does not imply real-customer accuracy.
- **Contamination.** Public data may already be in the base model's pretraining. Treat external scores
  as a robustness check, not a clean held-out estimate. The internal family-held-out split remains
  the leakage-controlled test.
- **Small n.** 50 τ³ tasks gives a coarse estimate; report confidence intervals, not just a point
  score.
- **No model yet.** Every external score for the tuned model is **NOT RUN** until the QLoRA adapter
  and GGUF exist. Do not fill these rows with rules-baseline numbers.

## 10. What has and has not run

```
DONE   — Bitext / CLINC150 / BANKING77 external NLU probe against the rules baseline
         (EVALUATION_RESULTS/external-nlu-rules.{json,md})
NOT RUN — τ³ retail adapter and 50-task evaluation (needs API keys + tool mapping)
NOT RUN — AgentDojo / InjecAgent mapped injection evaluation (no untrusted content channel)
NOT RUN — LLM-judge or human rubric for response quality
NOT RUN — any result for the tuned model (adapter/GGUF do not exist)
```

The published dataset facts in §2–§4 are verified against the publishers' cards. Raw rows are cached
under `artifacts/external/` (gitignored), not committed. The NLU artifact is a reference-backend
result and must never be presented as a tuned-model score.

## 11. Next actions

1. **Done (offline, no keys):** `eval/external/nlu_probe.py` covers Bitext, BANKING77 and CLINC150;
   output `EVALUATION_RESULTS/external-nlu-rules.{json,md}`; 4 unit tests in
   `tests/test_external_nlu.py`.
2. **P1 (blocked on keys):** τ³ retail adapter + 50-task evaluation. Freeze the user-simulator model
   and map tools before running; report `pass^1`, `pass^3` and forbidden mutations.
3. **P2 (blocked on design):** add a deliberately untrusted content channel, then run a mapped
   AgentDojo/InjecAgent subset. Only then update the scorecard's generalisation and security rows.
4. **P3 (needs a rater/judge):** response-quality rubric on 100 stratified cases; calibrate the
   judge against 30 human labels before trusting it.

## 12. Sources (accessed 2026-10-23)

- τ³-bench: <https://github.com/sierra-research/tau2-bench> · <https://arxiv.org/abs/2506.07982>
- τ-bench (outdated, retained for history): <https://github.com/sierra-research/tau-bench>
- Bitext: <https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset>
- BANKING77: <https://huggingface.co/datasets/PolyAI/banking77> · <https://arxiv.org/abs/2003.04807>
- CLINC150: <https://huggingface.co/datasets/clinc/clinc_oos> · <https://github.com/clinc/oos-eval>
- AgentDojo: <https://github.com/ethz-spylab/agentdojo> · <https://arxiv.org/abs/2406.13352>
- InjecAgent: <https://github.com/uiuc-kang-lab/InjecAgent> · <https://arxiv.org/abs/2403.02691>
- SGD: <https://github.com/google-research-datasets/dstc8-schema-guided-dialogue>
- MASSIVE: <https://huggingface.co/datasets/AmazonScience/massive> · <https://arxiv.org/abs/2204.08582>

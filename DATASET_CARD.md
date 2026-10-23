# Dataset card — Northwind Support SFT v0.1

**Status:** generated and validated on this machine. Not yet used for training (no GPU).

## Summary

| Field | Value |
|---|---|
| Path | `data/sft/train.jsonl`, `data/sft/dev.jsonl` (gitignored; regenerate with `python -m data_gen.generate --variants 4`) |
| Generator | `data_gen/generate.py` |
| Validator | `data_gen/validate.py` → `EVALUATION_RESULTS/dataset-validation.json` |
| Train / dev examples | **2,796 / 312** |
| Scenario cases | 280 used for SFT; 30 adversarial scenarios excluded |
| Variants per case | 4 (surface rephrasings) |
| Families | 13 |
| Held-out dev families | `human_handoff`, `multi_item_ambiguity`, `refund_already_refunded` |
| Excluded adversarial families | `cross_account`, `prompt_injection` |
| Teacher | rules baseline + deterministic policy engine (no external LLM) |
| Seed | 11 |
| PII | none — synthetic names, `example.test` emails, fake orders |

## Composition

Each scenario yields three supervised tasks:

| Task | Input | Gold output |
|---|---|---|
| `understand` | customer message | intent, entities, `needs_clarification`, question, confidence |
| `act` | message + understanding | the tool sequence actually executed, with real arguments, plus the resolution |
| `respond` | message + verified action result | customer reply, citations, escalation flag |

Gold labels come from running the reference agent against a per-case database, so the reply is grounded
in real rows (amounts, RMA codes, statuses) rather than invented text.

Families and counts (scenario level):

| Family | n | Family | n |
|---|---|---|---|
| refund_eligible | 35 | cancellation | 20 |
| order_status | 30 | warranty | 20 |
| return_eligible | 30 | refund_already_refunded | 15 |
| refund_out_of_window | 25 | missing_information | 15 |
| refund_over_threshold | 25 | multi_item_ambiguity | 10 |
| replacement_damaged | 25 | human_handoff | 10 |
| refund_final_sale | 20 | | |

`cross_account` (15 scenarios) and `prompt_injection` (15 scenarios) are deliberately **not** in the
SFT data; they form the held-out adversarial evaluation in `eval/adversarial.py`. Counts above sum to
280 used scenarios.

## Splitting

Splits are **by scenario family**, not by row. The three held-out dev families never appear in
`train.jsonl` in any variant, so `dev` measures behaviour on unseen task types. The validator fails the
build if any family name appears in both splits. The two adversarial families are excluded from both
splits and evaluated separately, so the tuned model cannot memorise the attacks it is scored on.

Exact-duplicate message sets are removed during generation (`dropped` in the run output); the validator
independently re-checks for duplicates.

## Validation performed

`data_gen/validate.py` checks, per line: JSON parses; `task` is known; `messages`, `response`, `meta`
present; the response parses as JSON and contains the task's required keys; `customer_message` is
non-empty for `respond`; message sets are unique; and no family crosses the split boundary.

Result: `{"ok": true, "errors": [], "rows": {"train": 2796, "dev": 312}}`.

`data_gen/spotcheck.py` samples 50 rows by stride (35 train, 15 dev) and audits properties the schema
cannot see: an order id in the message must be extracted; deny-only families must carry no mutating
tool and must not claim success; read-only families must not mutate; replies must name the order they
answer about; no placeholder text or non-`example.test` email addresses. Result: **0 findings**
(`EVALUATION_RESULTS/dataset-spotcheck.json`).

The spot-check caught two real defects on its first run, both fixed at the source and the dataset
regenerated: an order-status reply that said "delivered and hasn't shipped yet", and a clarification
question that suggested the fixture id `ORD-1001`.

## Intended use

Supervised fine-tuning of `Qwen2.5-3B-Instruct` to emit the three stage schemas in this repository. It is
a behaviour-cloning dataset for a bounded agent, not a general chat corpus.

## Limitations

- **Templated.** Four variants per case are surface rephrasings (prefix/suffix), not independent
  scenarios. Diversity is low by design; the manifest says so.
- **Teacher is the baseline.** The dataset inherits the baseline's keyword-driven intent errors. A model
  trained on it may reproduce them.
- **Synthetic only.** No real transcripts, accents, typos, code-switching, or multi-intent messages.
- **Small.** 2,796 examples is a smoke-scale SFT set for a 3B model. Scaling needs more templates,
  handwritten paraphrases, and real (consented) transcripts.
- **Adversarial refusal is not supervised.** Injection and cross-account families are excluded, so the
  model has no positive examples of refusing them; the policy/tool layer is the enforcement point.
- **Class imbalance.** Refund and status families dominate; complaint tone and payment disputes are thin.
- **Labels encode policy version 2026.1.** If `policy.py` changes, the dataset must be regenerated rather
  than patched.

## Ethical and legal

Synthetic data; no personal data was collected or processed. Generated content is released with the
repository. The base model's licence (Apache-2.0) applies to derivatives.

## Maintenance

```powershell
python -m data_gen.generate --variants 4   # regenerate
python -m data_gen.validate                # must print "ok": true
```

Regenerate after any change to `policy.py`, `seed.py`, the scenario generator, or the reply templates,
then re-run `python -m eval.harness` to confirm the reference still passes.

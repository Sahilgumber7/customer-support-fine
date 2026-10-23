# Response-quality rubric (100 cases)

**Status: NOT RUN — no labels collected.** The exported sample is in `items.jsonl`; it is not a score.

## What is scored

Each item contains the customer message, the assistant reply, the action/reason, and the ground-truth
fixture (order status, owner, expected action, expected no-mutation). Judge the **reply**, not the
policy engine's internal decision. Use the fixture to detect invented facts.

## Dimensions (1-5 each)

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| `factuality` | invents facts | one vague claim | all claims grounded |
| `policy_adherence` | promises ineligible action | right outcome, weak reason | right outcome + reason |
| `completeness` | misses question/next step | omits a detail | full answer + next step |
| `clarity_empathy` | confusing or dismissive | flat | clear, concise, empathetic |

`unsupported_claims` is a separate 0/1 flag: 1 if the reply asserts a fact or completed action that the
fixture/action does not support.

## Label format

One JSON object per line:

```json
{"item_id":"order-001","rater_id":"rater-1","factuality":5,"policy_adherence":5,"completeness":4,"clarity_empathy":4,"unsupported_claims":0,"notes":""}
```

Do not edit `items.jsonl`. Score with:

```powershell
$env:PYTHONPATH="src;."
python -m eval.rubric --score data/rubric/labels.rater-1.jsonl
```

A second rater should label independently; report agreement before averaging. The scorecard's
response-quality row stays **NOT MEASURED** until labels exist.

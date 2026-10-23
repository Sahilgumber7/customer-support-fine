"""Export and score the 100-case response-quality rubric.

The rubric is intentionally human-scored. This script exports a deterministic, stratified sample of
100 benchmark cases with the reference backend's reply and the ground-truth fixture, then validates and
summarises label files when they exist. No labels are invented; without labels the result is NOT RUN.

Run:
    $env:PYTHONPATH="src;."
    python -m eval.rubric --export
    python -m eval.rubric --score data/rubric/labels.rater-1.jsonl

Outputs:
    data/rubric/items.jsonl
    data/rubric/RUBRIC.md
    EVALUATION_RESULTS/rubric-export.json
    (with --score) EVALUATION_RESULTS/rubric-scores.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from eval.harness import Case, build_env, generate
from support_ai.db import Order
from support_ai.llm import RulesBackend
from support_ai.orchestrator import Orchestrator
from support_ai.retrieval import Retriever

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data" / "rubric" / "items.jsonl"
RUBRIC = ROOT / "data" / "rubric" / "RUBRIC.md"
RESULTS = ROOT / "EVALUATION_RESULTS"

DIMENSIONS = ("factuality", "policy_adherence", "completeness", "clarity_empathy")


def stratified_sample(cases: list[Case], n: int = 100) -> list[Case]:
    """Round-robin by family so every family is represented before any family gets a second row."""
    buckets: dict[str, list[Case]] = {}
    for case in cases:
        buckets.setdefault(case.family, []).append(case)
    order = sorted(buckets)
    picked: list[Case] = []
    index = 0
    while len(picked) < n:
        added = False
        for family in order:
            bucket = buckets[family]
            if index < len(bucket) and len(picked) < n:
                picked.append(bucket[index])
                added = True
        if not added:
            break
        index += 1
    return picked


def item_for(case: Case, backend: RulesBackend, retriever: Retriever) -> dict:
    session, conv_id, _ = build_env(case, retriever)
    try:
        result = Orchestrator(session, backend, retriever, 1, conv_id).handle(case.message)
        order = session.get(Order, case.order_id)
        return {
            "id": case.id,
            "family": case.family,
            "customer_message": case.message,
            "assistant_message": result.message,
            "action_taken": result.action_taken,
            "reason_code": result.reason_code,
            "fixture": {
                "order_id": case.order_id or None,
                "sku": case.sku,
                "owner_customer_id": case.owner,
                "status": None if order is None else order.status,
                "delivered_days_ago": case.delivered_days,
                "expected_action": case.expect_action,
                "expected_no_mutation": case.expect_no_mutation,
                "expected_amount_cents": case.expect_amount,
            },
        }
    finally:
        session.close()


def export() -> None:
    retriever = Retriever.from_directory()
    picked = stratified_sample(generate(), 100)
    items = [item_for(case, RulesBackend(), retriever) for case in picked]
    ITEMS.parent.mkdir(parents=True, exist_ok=True)
    ITEMS.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in items) + "\n",
        encoding="utf-8",
    )
    RUBRIC.write_text(RUBRIC_TEXT, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "NOT RUN — no labels collected",
        "backend": "rules-baseline",
        "n_items": len(items),
        "by_family": dict(sorted(Counter(item["family"] for item in items).items())),
        "items_path": str(ITEMS.relative_to(ROOT)),
        "rubric_path": str(RUBRIC.relative_to(ROOT)),
        "dimensions": list(DIMENSIONS),
        "scale": "1-5 per dimension; unsupported_claims is a 0/1 flag",
        "note": (
            "This is a response-quality sample, not a score. The scorecard's 15-point response row "
            "stays NOT MEASURED until at least one human rater labels all 100 items."
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "rubric-export.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(f"exported {len(items)} items -> {ITEMS}")
    print(f"status: {payload['status']}")


def score(labels_path: Path) -> None:
    items = {json.loads(line)["id"] for line in ITEMS.read_text(encoding="utf-8").splitlines()}
    labels = [json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines()]
    errors: list[str] = []
    seen: set[str] = set()
    for lineno, label in enumerate(labels, 1):
        item_id = label.get("item_id")
        if item_id not in items:
            errors.append(f"line {lineno}: unknown item_id {item_id!r}")
        if item_id in seen:
            errors.append(f"line {lineno}: duplicate item_id {item_id!r}")
        seen.add(item_id)
        for dimension in DIMENSIONS:
            value = label.get(dimension)
            if not isinstance(value, int) or not 1 <= value <= 5:
                errors.append(f"line {lineno}: {dimension} must be an int 1-5")
        if label.get("unsupported_claims") not in (0, 1):
            errors.append(f"line {lineno}: unsupported_claims must be 0 or 1")
    if errors:
        raise SystemExit("\n".join(errors[:20]))

    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "labels_path": str(labels_path),
        "n_labeled": len(labels),
        "n_items": len(items),
        "complete": len(labels) == len(items),
        "means": {
            dimension: round(sum(label[dimension] for label in labels) / len(labels), 3)
            for dimension in DIMENSIONS
        },
        "unsupported_claim_rate": round(
            sum(label["unsupported_claims"] for label in labels) / len(labels), 3
        ),
        "note": "Descriptive means only; the weighted scorecard is not changed by this run.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "rubric-scores.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="export the 100-case sample")
    parser.add_argument("--score", type=Path, help="score a JSONL label file")
    args = parser.parse_args()
    if not args.export and not args.score:
        parser.error("choose --export or --score")
    if args.export:
        export()
    if args.score:
        score(args.score)


RUBRIC_TEXT = """# Response-quality rubric (100 cases)

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
"""


if __name__ == "__main__":
    main()

"""Deterministic spot-check of the generated SFT data.

Not a substitute for human reading; it is the automated half. It samples rows by stride,
re-parses every label, and checks the properties that would be embarrassing to get wrong:

- an order id in the message must appear in the extracted entities;
- deny-only families must not carry a mutating tool in their `act` label;
- deny-only families must not claim success in their `respond` label;
- no placeholder text and no non-example email addresses.

Run: ``python -m data_gen.spotcheck``
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "EVALUATION_RESULTS"

MUTATING = {
    "submit_refund_request",
    "create_return_request",
    "create_replacement_request",
    "request_cancellation",
    "create_support_ticket",
    "escalate_to_human",
}

DENY_FAMILIES = {
    "refund_out_of_window",
    "refund_final_sale",
    "refund_already_refunded",
    "cross_account",
    "prompt_injection",
}

REQUIRED_ACTION = {
    "refund_eligible": {"submit_refund_request"},
    "return_eligible": {"create_return_request"},
    "replacement_damaged": {"create_replacement_request"},
}

SUCCESS_WORDS = ("done", "has been issued", "have issued", "has been created", "is on its way")

ORDER_RE = re.compile(r"ORD-\d{4}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+")
PLACEHOLDERS = ("TODO", "lorem ipsum", "XXX", "{order", "<insert")


def load(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing {path}; run python -m data_gen.generate --variants 4")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sample(rows: list[dict], n: int) -> list[dict]:
    stride = max(1, len(rows) // n)
    return rows[::stride][:n]


def check(row: dict) -> list[str]:
    problems: list[str] = []
    family = row["meta"]["family"]
    user = next(m["content"] for m in row["messages"] if m["role"] == "user")
    try:
        label = json.loads(row["response"])
    except json.JSONDecodeError:
        return ["response is not JSON"]

    joined = json.dumps(row)
    for marker in PLACEHOLDERS:
        if marker in joined:
            problems.append(f"placeholder {marker!r}")
    for email in EMAIL_RE.findall(joined):
        if not email.endswith("example.test"):
            problems.append(f"non-example email {email}")

    order_ids = set(ORDER_RE.findall(user))
    if row["task"] == "understand":
        found = label.get("entities", {}).get("order_id")
        if order_ids and found not in order_ids:
            problems.append(f"order id {sorted(order_ids)} -> entity {found!r}")
        if not (0.0 <= float(label.get("confidence", -1)) <= 1.0):
            problems.append("confidence out of range")

    if row["task"] == "act":
        tools = [c["name"] for c in label.get("tool_calls", [])]
        if family in DENY_FAMILIES and MUTATING & set(tools):
            problems.append(f"deny family carries mutating tools {MUTATING & set(tools)}")
        expected = REQUIRED_ACTION.get(family)
        if expected and not expected & set(tools):
            problems.append(f"expected {sorted(expected)} in {tools}")
        if family in {"order_status", "missing_information", "multi_item_ambiguity"}:
            if MUTATING & set(tools):
                problems.append(f"read-only family carries {MUTATING & set(tools)}")

    if row["task"] == "respond":
        message = label.get("customer_message", "")
        if not message:
            problems.append("empty customer message")
        if family in DENY_FAMILIES:
            low = message.lower()
            for word in SUCCESS_WORDS:
                if word in low:
                    problems.append(f"deny family claims success: {word!r}")
        if order_ids and not any(o in message for o in order_ids):
            problems.append("reply omits the mentioned order id")
        low = message.lower()
        if "hasn't shipped yet" in low and "delivered" in low:
            problems.append("reply contradicts itself (delivered + not shipped)")
        if "looks like ORD-1001" in message:
            problems.append("clarification suggests a real fixture order id")

    return problems


def main() -> None:
    train = load(ROOT / "data" / "sft" / "train.jsonl")
    dev = load(ROOT / "data" / "sft" / "dev.jsonl")
    picked = sample(train, 35) + sample(dev, 15)

    findings = []
    counts: Counter[str] = Counter()
    for row in picked:
        problems = check(row)
        counts[row["task"]] += 1
        counts[f"family:{row['meta']['family']}"] += 1
        if problems:
            findings.append(
                {
                    "case_id": row["meta"]["case_id"],
                    "family": row["meta"]["family"],
                    "task": row["task"],
                    "problems": problems,
                }
            )

    report = {
        "sampled": len(picked),
        "train_rows": len(train),
        "dev_rows": len(dev),
        "by_task": {
            k: v for k, v in counts.items() if not k.startswith("family:")
        },
        "by_family": {
            k.split(":", 1)[1]: v for k, v in counts.items() if k.startswith("family:")
        },
        "findings": findings,
        "ok": not findings,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "dataset-spotcheck.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"sampled": report["sampled"], "findings": len(findings), "ok": report["ok"]},
            indent=2,
        )
    )
    for finding in findings:
        print(f"  {finding['case_id']} [{finding['family']}/{finding['task']}]: {finding['problems']}")


if __name__ == "__main__":
    main()

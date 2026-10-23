"""Validate the generated SFT dataset before spending GPU time.

Checks: schema per task, JSON-parseable gold responses, required fields, duplicate rows,
train/dev family separation, and label distribution.

Run: python -m data_gen.validate
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "understand": {"intent", "entities", "needs_clarification", "confidence"},
    "act": {"tool_calls", "proposed_resolution"},
    "respond": {"customer_message", "cites", "escalate"},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_split(path: Path) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    rows: list[dict] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{lineno} invalid json: {exc}")
            continue
        rows.append(row)
        for key in ("task", "messages", "response", "meta"):
            if key not in row:
                errors.append(f"{path.name}:{lineno} missing {key}")
        if row.get("task") not in REQUIRED:
            errors.append(f"{path.name}:{lineno} unknown task {row.get('task')}")
            continue
        try:
            payload = json.loads(row["response"])
        except (TypeError, json.JSONDecodeError):
            errors.append(f"{path.name}:{lineno} response is not JSON")
            continue
        missing = REQUIRED[row["task"]] - set(payload)
        if missing:
            errors.append(f"{path.name}:{lineno} response missing {sorted(missing)}")
        if row["task"] == "respond" and not str(payload.get("customer_message", "")).strip():
            errors.append(f"{path.name}:{lineno} empty customer_message")
        digest = json.dumps(row["messages"], sort_keys=True)
        if digest in seen:
            errors.append(f"{path.name}:{lineno} duplicate messages")
        seen.add(digest)
    return rows, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "sft"))
    parser.add_argument(
        "--out", default=str(ROOT / "EVALUATION_RESULTS" / "dataset-validation.json")
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    report: dict = {"splits": {}, "errors": []}
    families: dict[str, set[str]] = {}

    for split in ("train", "dev"):
        path = data_dir / f"{split}.jsonl"
        if not path.exists():
            report["errors"].append(f"missing {path}")
            continue
        rows, errors = validate_split(path)
        tasks = Counter(r.get("task") for r in rows)
        fams = Counter(r.get("meta", {}).get("family") for r in rows)
        intents = Counter(
            json.loads(r["response"]).get("intent")
            for r in rows
            if r.get("task") == "understand" and r.get("response")
        )
        families[split] = set(fams)
        report["splits"][split] = {
            "path": str(path),
            "rows": len(rows),
            "sha256": sha256(path),
            "tasks": dict(tasks),
            "families": dict(fams),
            "intents": {k: v for k, v in intents.items() if k},
        }
        report["errors"].extend(errors)

    if "train" in families and "dev" in families:
        overlap = families["train"] & families["dev"]
        report["family_leakage"] = sorted(overlap)
        if overlap:
            report["errors"].append(f"family leakage: {sorted(overlap)}")

    report["ok"] = not report["errors"]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "errors": report["errors"][:10],
                "rows": {k: v["rows"] for k, v in report["splits"].items()},
            },
            indent=2,
        )
    )
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()

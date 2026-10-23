"""Offline external NLU probe: Bitext intents, BANKING77 OOD, CLINC150 OOS.

This is a *reference-backend* probe, not a tuned-model score. It exists to test whether the
keyword rules generalise to public customer-support phrasings, and to measure how often the
agent accepts requests from domains it cannot serve.

Run:
    $env:PYTHONPATH="src;."
    python -m eval.external.nlu_probe

Outputs:
    EVALUATION_RESULTS/external-nlu-rules.json
    EVALUATION_RESULTS/external-nlu-rules.md

Raw datasets are cached under artifacts/external/ (gitignored). Nothing is sent to a model API.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from support_ai.llm import RulesBackend
from support_ai.schemas import Intent

BITEXT_URL = (
    "https://huggingface.co/datasets/bitext/"
    "Bitext-customer-support-llm-chatbot-training-dataset/resolve/main/"
    "Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv?download=true"
)
BITEXT_REVISION = "430d1a89bd93bd1fa23c16f29dd53e73f0087443"
BANKING77_URL = (
    "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/"
    "banking_data/test.csv"
)
CLINC150_URL = "https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json"

# Only intents whose *action* maps unambiguously. Questions (check_refund_policy,
# check_cancellation_fee), order edits, shipping/account operations and invoices are excluded;
# treating them as one of our intents would inflate or deflate the score for no defensible reason.
BITEXT_INTENT_MAP: dict[str, Intent] = {
    "cancel_order": "cancellation_request",
    "get_refund": "refund_request",
    "track_refund": "refund_request",
    "track_order": "order_status",
    "contact_human_agent": "human_handoff",
    "contact_customer_service": "human_handoff",
    "complaint": "complaint",
    "payment_issue": "payment_issue",
}
ACCEPTABLE_OOD = {"other", "human_handoff"}


def fetch(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "support-ai-external-eval/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        data = response.read()
    if not data:
        raise RuntimeError(f"empty response from {url}")
    path.write_bytes(data)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classification_metrics(
    pairs: Iterable[tuple[str, str]], labels: list[str]
) -> dict[str, object]:
    """Accuracy, per-label P/R/F1 and macro-F1 from (true, predicted) pairs."""
    pairs = list(pairs)
    counts = Counter(pairs)
    per_label: dict[str, dict[str, float | int]] = {}
    f1s: list[float] = []
    for label in labels:
        tp = counts[(label, label)]
        fp = sum(v for (true, pred), v in counts.items() if pred == label and true != label)
        fn = sum(v for (true, pred), v in counts.items() if true == label and pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1s.append(f1)
        per_label[label] = {
            "support": tp + fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    total = len(pairs)
    correct = sum(1 for true, pred in pairs if true == pred)
    return {
        "n": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0,
        "per_label": per_label,
        "confusion": {
            f"{true} -> {pred}": count
            for (true, pred), count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        },
    }


def ood_summary(predicted: Iterable[str]) -> dict[str, object]:
    predicted = list(predicted)
    counts = Counter(predicted)
    accepted = [intent for intent in predicted if intent not in ACCEPTABLE_OOD]
    acceptable = len(predicted) - len(accepted)
    return {
        "n": len(predicted),
        "acceptable": acceptable,
        "acceptable_rate": round(acceptable / len(predicted), 4) if predicted else 0.0,
        "false_accepts": len(accepted),
        "false_accept_rate": round(len(accepted) / len(predicted), 4) if predicted else 0.0,
        "handoff_rate": round(counts["human_handoff"] / len(predicted), 4) if predicted else 0.0,
        "other_rate": round(counts["other"] / len(predicted), 4) if predicted else 0.0,
        "accepted_by_intent": {
            intent: count for intent, count in counts.most_common() if intent not in ACCEPTABLE_OOD
        },
    }


def run_bitext(path: Path, backend: RulesBackend) -> dict[str, object]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    mapped_pairs: list[tuple[str, str]] = []
    unmapped_predictions: list[str] = []
    unmapped = 0
    for row in rows:
        true_intent = BITEXT_INTENT_MAP.get(row["intent"].strip())
        predicted = backend.understand(row["instruction"], []).intent
        if true_intent is None:
            unmapped += 1
            unmapped_predictions.append(predicted)
        else:
            mapped_pairs.append((true_intent, predicted))
    labels = sorted(set(BITEXT_INTENT_MAP.values()))
    metrics = classification_metrics(mapped_pairs, labels)
    unmapped_in_scope = sum(1 for intent in unmapped_predictions if intent not in ACCEPTABLE_OOD)
    return {
        "source_url": BITEXT_URL,
        "revision": BITEXT_REVISION,
        "sha256": sha256(path),
        "rows": len(rows),
        "mapped_rows": len(mapped_pairs),
        "unmapped_rows": unmapped,
        "mapping": BITEXT_INTENT_MAP,
        "mapping_sha256": hashlib.sha256(
            json.dumps(BITEXT_INTENT_MAP, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "metrics": metrics,
        "unmapped_overreach": {
            "n": unmapped,
            "in_scope_predictions": unmapped_in_scope,
            "in_scope_rate": round(unmapped_in_scope / unmapped, 4) if unmapped else 0.0,
        },
    }


def run_banking77(path: Path, backend: RulesBackend) -> dict[str, object]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    predictions = [backend.understand(row["text"], []).intent for row in rows]
    return {
        "source_url": BANKING77_URL,
        "sha256": sha256(path),
        "rows": len(rows),
        "scope": "all rows are out-of-domain for a retailer",
        **ood_summary(predictions),
    }


def run_clinc150(path: Path, backend: RulesBackend) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["oos_test"]
    if any(label != "oos" for _, label in rows):
        raise RuntimeError("CLINC150 oos_test contains a non-oos label")
    predictions = [backend.understand(text, []).intent for text, _ in rows]
    return {
        "source_url": CLINC150_URL,
        "sha256": sha256(path),
        "rows": len(rows),
        "scope": "CLINC150 out-of-scope test split",
        **ood_summary(predictions),
    }


def render_markdown(result: dict[str, object]) -> str:
    bitext = result["datasets"]["bitext"]  # type: ignore[index]
    banking = result["datasets"]["banking77"]  # type: ignore[index]
    clinc = result["datasets"]["clinc150"]  # type: ignore[index]
    bitext_metrics = bitext["metrics"]  # type: ignore[index]
    lines = [
        "# External NLU probe — rules baseline",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "> **Reference backend only.** This measures the deterministic keyword baseline, not the "
        "fine-tuned model (which is NOT RUN). External data is evaluation-only; raw rows are not "
        "committed.",
        "",
        "## Bitext customer support (mapped intents)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Rows | {bitext['rows']:,} |",
        f"| Mapped rows | {bitext['mapped_rows']:,} |",
        f"| Unmapped rows | {bitext['unmapped_rows']:,} |",
        f"| Accuracy | {bitext_metrics['accuracy']:.2%} |",
        f"| Macro-F1 | {bitext_metrics['macro_f1']:.4f} |",
        f"| Unmapped rows given an in-scope intent | "
        f"{bitext['unmapped_overreach']['in_scope_predictions']:,} "
        f"({bitext['unmapped_overreach']['in_scope_rate']:.2%}) |",
        "",
        "| Intent | Support | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, row in bitext_metrics["per_label"].items():
        lines.append(
            f"| {label} | {row['support']:,} | {row['precision']:.3f} | "
            f"{row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines += [
        "",
        "## BANKING77 (out-of-domain rejection)",
        "",
        f"All {banking['n']:,} test queries are out-of-domain for this retailer. "
        f"Acceptable = `other` or `human_handoff`.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| False accepts | {banking['false_accepts']:,} |",
        f"| False-accept rate | {banking['false_accept_rate']:.2%} |",
        f"| Handoff rate | {banking['handoff_rate']:.2%} |",
        f"| Other rate | {banking['other_rate']:.2%} |",
        "",
        "| Predicted in-scope intent | Count |",
        "|---|---:|",
    ]
    for intent, count in banking["accepted_by_intent"].items():
        lines.append(f"| {intent} | {count:,} |")
    lines += [
        "",
        "## CLINC150 (out-of-scope recall)",
        "",
        f"The {clinc['n']:,} `oos_test` rows should all be refused or handed off.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| OOS recall (acceptable rate) | {clinc['acceptable_rate']:.2%} |",
        f"| False accepts | {clinc['false_accepts']:,} |",
        f"| False-accept rate | {clinc['false_accept_rate']:.2%} |",
        f"| Handoff rate | {clinc['handoff_rate']:.2%} |",
        "",
        "## Provenance",
        "",
        "| Dataset | Source | SHA-256 |",
        "|---|---|---|",
        f"| Bitext | {BITEXT_URL.split('?')[0]} (revision `{BITEXT_REVISION[:12]}`) | "
        f"`{bitext['sha256'][:16]}…` |",
        f"| BANKING77 | {BANKING77_URL} | `{banking['sha256'][:16]}…` |",
        f"| CLINC150 | {CLINC150_URL} | `{clinc['sha256'][:16]}…` |",
        "",
        "Machine-readable result: `EVALUATION_RESULTS/external-nlu-rules.json`.",
        "",
    ]
    return "\n".join(lines)


def run(cache_dir: Path, out_dir: Path, backend: RulesBackend) -> dict[str, object]:
    bitext_path = cache_dir / "bitext_customer_support.csv"
    banking_path = cache_dir / "banking77_test.csv"
    clinc_path = cache_dir / "clinc150_data_full.json"
    fetch(BITEXT_URL, bitext_path)
    fetch(BANKING77_URL, banking_path)
    fetch(CLINC150_URL, clinc_path)

    result: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "backend": {
            "id": "rules-baseline",
            "model_id": backend.model_id,
            "kind": "deterministic keyword baseline",
        },
        "disclaimer": (
            "Reference backend only; not tuned-model quality. External datasets are evaluation-only "
            "and were not used for SFT."
        ),
        "datasets": {
            "bitext": run_bitext(bitext_path, backend),
            "banking77": run_banking77(banking_path, backend),
            "clinc150": run_clinc150(clinc_path, backend),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "external-nlu-rules.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "external-nlu-rules.md").write_text(render_markdown(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path("artifacts/external"))
    parser.add_argument("--out", type=Path, default=Path("EVALUATION_RESULTS"))
    args = parser.parse_args()
    result = run(args.cache_dir, args.out, RulesBackend())
    bitext = result["datasets"]["bitext"]  # type: ignore[index]
    banking = result["datasets"]["banking77"]  # type: ignore[index]
    clinc = result["datasets"]["clinc150"]  # type: ignore[index]
    print(
        f"Bitext mapped: {bitext['mapped_rows']:,} rows, "
        f"accuracy {bitext['metrics']['accuracy']:.2%}, "
        f"macro-F1 {bitext['metrics']['macro_f1']:.3f}"
    )
    print(
        f"BANKING77 OOD: {banking['false_accepts']:,}/{banking['n']:,} false accepts "
        f"({banking['false_accept_rate']:.2%})"
    )
    print(
        f"CLINC150 OOS: recall {clinc['acceptable_rate']:.2%}, "
        f"{clinc['false_accepts']:,}/{clinc['n']:,} false accepts"
    )
    print(f"Wrote {args.out / 'external-nlu-rules.json'} and .md")


if __name__ == "__main__":
    main()

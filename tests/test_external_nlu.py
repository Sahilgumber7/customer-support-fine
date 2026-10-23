from __future__ import annotations

from typing import get_args

from eval.external.nlu_probe import (
    ACCEPTABLE_OOD,
    BITEXT_INTENT_MAP,
    classification_metrics,
    ood_summary,
)
from support_ai.schemas import Intent


def test_bitext_mapping_only_uses_project_intents() -> None:
    valid = set(get_args(Intent))
    assert set(BITEXT_INTENT_MAP.values()) <= valid
    assert ACCEPTABLE_OOD <= valid


def test_classification_metrics_are_computed_from_pairs() -> None:
    pairs = [
        ("refund_request", "refund_request"),
        ("refund_request", "other"),
        ("order_status", "order_status"),
        ("order_status", "refund_request"),
    ]
    metrics = classification_metrics(pairs, ["order_status", "refund_request"])

    assert metrics["n"] == 4
    assert metrics["accuracy"] == 0.5
    assert metrics["per_label"]["refund_request"]["support"] == 2
    assert metrics["per_label"]["refund_request"]["precision"] == 0.5
    assert metrics["per_label"]["refund_request"]["recall"] == 0.5
    assert metrics["macro_f1"] == 0.5833
    assert metrics["confusion"]["refund_request -> other"] == 1


def test_ood_summary_treats_other_and_handoff_as_acceptable() -> None:
    summary = ood_summary(["other", "human_handoff", "refund_request", "order_status"])

    assert summary["n"] == 4
    assert summary["acceptable"] == 2
    assert summary["false_accepts"] == 2
    assert summary["false_accept_rate"] == 0.5
    assert summary["handoff_rate"] == 0.25
    assert summary["accepted_by_intent"] == {"refund_request": 1, "order_status": 1}


def test_empty_ood_input_does_not_divide_by_zero() -> None:
    summary = ood_summary([])

    assert summary["n"] == 0
    assert summary["false_accept_rate"] == 0.0
    assert summary["handoff_rate"] == 0.0

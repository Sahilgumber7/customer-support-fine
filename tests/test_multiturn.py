from __future__ import annotations

from eval.multiturn import cases, run
from support_ai.llm import RulesBackend
from support_ai.retrieval import Retriever


def test_rules_backend_carries_order_from_previous_user_turn() -> None:
    history = [
        {"role": "user", "content": "Where is ORD-1010?"},
        {"role": "assistant", "content": "ORD-1010 was delivered."},
    ]
    understanding = RulesBackend().understand("Can I get a refund for it? It's damaged.", history)

    assert understanding.intent == "refund_request"
    assert understanding.entities.order_id == "ORD-1010"
    assert understanding.needs_clarification is False


def test_rules_backend_carries_intent_after_clarification() -> None:
    history = [
        {"role": "user", "content": "My order is broken."},
        {
            "role": "assistant",
            "content": "Could you share the order number so I can look into this for you?",
        },
    ]
    understanding = RulesBackend().understand("The order number is ORD-1004, it's the lamp.", history)

    assert understanding.intent == "refund_request"
    assert understanding.entities.order_id == "ORD-1004"
    assert understanding.entities.reason_code == "damaged"


def test_carryover_ignores_assistant_invented_order_id() -> None:
    history = [
        {"role": "user", "content": "I need help."},
        {"role": "assistant", "content": "Do you mean ORD-9999?"},
    ]
    understanding = RulesBackend().understand("Please refund it, it's damaged.", history)

    assert understanding.entities.order_id is None
    assert understanding.needs_clarification is True


def test_multiturn_cases_are_unique_and_cover_six_families() -> None:
    suite = cases()
    ids = [case.id for case in suite]
    families = {case.family for case in suite}

    assert len(ids) == len(set(ids))
    assert len(suite) >= 40
    assert families >= {
        "context_carryover",
        "clarification",
        "correction",
        "intent_switch",
        "adversarial",
        "retry",
    }


def test_multiturn_runner_passes_a_context_case() -> None:
    rows = run([cases()[0]], RulesBackend(), Retriever.from_directory())

    assert rows[0]["passed"] is True
    assert rows[0]["failures"] == []

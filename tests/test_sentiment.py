"""Tests for customer sentiment, frustration detection, and contextual handoff summaries."""

from support_ai.sentiment import (
    CSATFeedback,
    analyze_sentiment,
    generate_handoff_briefing,
)


def test_positive_sentiment():
    verdict = analyze_sentiment("Thank you so much! That was really helpful and great.")
    assert verdict.label == "positive"
    assert verdict.sentiment_score > 0
    assert verdict.is_escalation_candidate is False


def test_frustration_and_escalation():
    verdict = analyze_sentiment("This is ridiculous! I want to speak to a human manager immediately!!")
    assert verdict.label == "frustrated"
    assert verdict.sentiment_score < 0
    assert verdict.is_escalation_candidate is True
    assert len(verdict.triggers) > 0


def test_caps_lock_frustration():
    verdict = analyze_sentiment("GIVE ME MY MONEY BACK NOW THIS IS A FRAUD")
    assert verdict.label == "frustrated"
    assert verdict.is_escalation_candidate is True


def test_neutral_sentiment():
    verdict = analyze_sentiment("What is the status of my order ORD-1001?")
    assert verdict.label == "neutral"
    assert verdict.is_escalation_candidate is False


def test_handoff_briefing_generation():
    briefing = generate_handoff_briefing(
        customer_id="CUST-001",
        original_message="I AM FURIOUS, MY ORDER ORD-1002 HAS NOT ARRIVED!",
        intent="order_status",
        entities={"order_id": "ORD-1002"},
        attempted_tools=["get_order", "get_shipment_status"],
        escalation_reason="customer_frustration_and_delay",
    )
    assert briefing["priority"] in ("HIGH", "CRITICAL")
    assert briefing["customer_id"] == "CUST-001"
    assert "ORD-1002" in str(briefing["entities"])
    assert "get_order" in briefing["attempted_tools"]
    assert "handoff_summary" in briefing
    assert "recommended_action" in briefing


def test_csat_feedback_model():
    csat = CSATFeedback(
        conversation_id="conv-123",
        customer_id="CUST-002",
        rating=5,
        issue_resolved=True,
        feedback_notes="Instant response, resolved my return within 30 seconds!",
    )
    assert csat.rating == 5
    assert csat.issue_resolved is True

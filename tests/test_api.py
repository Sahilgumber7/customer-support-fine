"""API integration tests against the real FastAPI app and a freshly seeded database."""

import pytest
from fastapi.testclient import TestClient

from support_ai.api import app
from support_ai.seed import reset_and_seed


@pytest.fixture(scope="module")
def client():
    reset_and_seed()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def customer_session(client):
    res = client.post("/api/login", json={"customer_id": 1})
    assert res.status_code == 200
    return {"X-Demo-Session": res.json()["token"]}


def test_health_and_readiness(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"


def test_model_info_states_what_is_served(client):
    info = client.get("/api/model-info").json()
    assert info["base_model"] == "Qwen/Qwen2.5-3B-Instruct"
    assert info["backend"] in {"mock", "llamacpp"}


def test_chat_round_trip(client, customer_session):
    conv = client.post("/api/conversations", headers=customer_session, json={}).json()
    res = client.post(
        f"/api/conversations/{conv['conversation_id']}/messages",
        headers=customer_session,
        json={"message": "Where is ORD-1001?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "order_status"
    assert "delivered" in body["message"].lower()

    history = client.get(
        f"/api/conversations/{conv['conversation_id']}", headers=customer_session
    ).json()
    roles = [m["role"] for m in history["messages"]]
    assert roles == ["user", "assistant"]


def test_unauthenticated_chat_is_rejected(client):
    assert client.post("/api/conversations", json={}).status_code == 401


def test_conversations_are_not_shared_between_customers(client, customer_session):
    conv = client.post("/api/conversations", headers=customer_session, json={}).json()
    other = client.post("/api/login", json={"customer_id": 2}).json()
    res = client.get(
        f"/api/conversations/{conv['conversation_id']}",
        headers={"X-Demo-Session": other["token"]},
    )
    assert res.status_code == 404


def test_ops_approval_flow(client, customer_session):
    conv = client.post("/api/conversations", headers=customer_session, json={}).json()
    client.post(
        f"/api/conversations/{conv['conversation_id']}/messages",
        headers=customer_session,
        json={"message": "The watch from ORD-1005 is defective, please refund it."},
    )
    approvals = client.get("/api/ops/approvals").json()
    pending = [a for a in approvals if a["status"] == "pending" and a["amount_cents"] == 19900]
    assert pending, "high-value refund should create a pending approval"

    decision = client.post(
        f"/api/ops/approvals/{pending[0]['id']}",
        json={"decision": "approve", "note": "verified with customer"},
    )
    assert decision.status_code == 200
    assert decision.json()["refund_status"] == "processed"

    audit = client.get("/api/ops/audit").json()
    assert any(a["action"] == "approval_decision" for a in audit)


def test_sentiment_api_analysis(client):
    res = client.post(
        "/api/sentiment/analyze",
        json={"message": "I am furious, this is ridiculous! Speak to a human immediately!!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["label"] == "frustrated"
    assert data["is_escalation_candidate"] is True
    assert data["urgency_score"] > 0


def test_csat_feedback_api(client):
    res = client.post(
        "/api/feedback/csat",
        json={
            "conversation_id": "conv-test-1",
            "customer_id": "CUST-001",
            "rating": 5,
            "issue_resolved": True,
            "feedback_notes": "Very fast resolution!",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "recorded"
    assert data["feedback"]["rating"] == 5

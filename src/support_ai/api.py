"""FastAPI surface: customer chat, ops console, health, and model provenance."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import (
    Approval,
    AuditLog,
    Conversation,
    Customer,
    Escalation,
    Message,
    Order,
    Refund,
    get_session,
    init_db,
)
from .llm import get_backend
from .orchestrator import Orchestrator, start_conversation
from .retrieval import Retriever
from .seed import reset_and_seed
from .sentiment import CSATFeedback, analyze_sentiment
from .web import CHAT_HTML, OPS_HTML


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with next(get_session()) as s:
        count = s.scalar(select(func.count()).select_from(Customer)) or 0
        if count == 0:
            reset_and_seed()
    yield


app = FastAPI(title="Northwind Support AI", version="0.1.0", lifespan=lifespan)
_retriever: Retriever | None = None
_backend = None
_sessions: dict[str, int] = {}


def retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever.from_directory()
    return _retriever


def backend():
    global _backend
    if _backend is None:
        _backend = get_backend()
    return _backend


# --- schemas ----------------------------------------------------------------


class LoginIn(BaseModel):
    customer_id: int


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ApprovalIn(BaseModel):
    decision: str = Field(pattern="^(approve|deny)$")
    note: str = ""


# --- auth (demo) ------------------------------------------------------------


def current_customer(
    x_demo_session: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Customer:
    if not x_demo_session or x_demo_session not in _sessions:
        raise HTTPException(status_code=401, detail="Not signed in. Select a demo customer first.")
    customer = session.get(Customer, _sessions[x_demo_session])
    if customer is None:
        raise HTTPException(status_code=401, detail="Session no longer valid.")
    return customer


def _owned_conversation(session: Session, conversation_id: int, customer_id: int) -> Conversation:
    conv = session.get(Conversation, conversation_id)
    if conv is None or conv.customer_id != customer_id:
        # Same response either way: no cross-account existence leak.
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


@app.post("/api/login")
def login(payload: LoginIn) -> dict:
    with next(get_session()) as s:
        customer = s.get(Customer, payload.customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="Unknown demo customer.")
        token = secrets.token_urlsafe(24)
        _sessions[token] = customer.id
        return {"token": token, "customer": {"id": customer.id, "name": customer.name}}


@app.get("/api/customers")
def customers() -> list[dict]:
    with next(get_session()) as s:
        return [
            {"id": c.id, "name": c.name} for c in s.scalars(select(Customer).order_by(Customer.id))
        ]


@app.get("/api/orders")
def my_orders(customer: Customer = Depends(current_customer)) -> list[dict]:
    with next(get_session()) as s:
        rows = s.scalars(select(Order).where(Order.customer_id == customer.id).order_by(Order.id))
        return [
            {
                "order_id": o.id,
                "status": o.status,
                "total_cents": o.total_cents,
                "placed_at": o.placed_at.isoformat(),
            }
            for o in rows
        ]


@app.post("/api/conversations")
def new_conversation(customer: Customer = Depends(current_customer)) -> dict:
    with next(get_session()) as s:
        conv = start_conversation(s, customer.id)
        return {"conversation_id": conv.id}


@app.get("/api/conversations/{conversation_id}")
def conversation_history(
    conversation_id: int, customer: Customer = Depends(current_customer)
) -> dict:
    with next(get_session()) as s:
        conv = _owned_conversation(s, conversation_id, customer.id)
        msgs = s.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
        )
        return {
            "conversation_id": conv.id,
            "status": conv.status,
            "messages": [{"role": m.role, "content": m.content} for m in msgs],
        }


@app.post("/api/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: int, payload: MessageIn, customer: Customer = Depends(current_customer)
) -> dict:
    with next(get_session()) as s:
        _owned_conversation(s, conversation_id, customer.id)
        orch = Orchestrator(s, backend(), retriever(), customer.id, conversation_id)
        result = orch.handle(payload.message)
        return result.model_dump()


# --- ops console ------------------------------------------------------------


def _require_ops(x_ops_token: str | None = Header(default=None)) -> None:
    if not settings.demo_mode and x_ops_token != "ops-secret":
        raise HTTPException(status_code=403, detail="Ops access required.")


@app.get("/api/ops/approvals")
def approvals(_: None = Depends(_require_ops)) -> list[dict]:
    with next(get_session()) as s:
        rows = s.scalars(select(Approval).order_by(Approval.id.desc()).limit(50))
        return [
            {
                "id": a.id,
                "refund_id": a.refund_id,
                "amount_cents": a.amount_cents,
                "reason": a.reason,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ]


@app.post("/api/ops/approvals/{approval_id}")
def decide_approval(approval_id: int, payload: ApprovalIn, _: None = Depends(_require_ops)) -> dict:
    with next(get_session()) as s:
        approval = s.get(Approval, approval_id)
        if approval is None or approval.status != "pending":
            raise HTTPException(status_code=409, detail="Approval not found or already decided.")
        refund = s.get(Refund, approval.refund_id) if approval.refund_id else None
        if refund is None:
            raise HTTPException(status_code=409, detail="Linked refund missing.")

        approval.status = "approved" if payload.decision == "approve" else "denied"
        approval.decided_at = datetime.now(UTC)
        if payload.decision == "approve":
            refund.status = "processed"
            order = s.get(Order, refund.order_id)
            if order is not None:
                already = sum(
                    r.amount_cents
                    for r in s.scalars(select(Refund).where(Refund.order_id == order.id))
                    if r.status in {"processed", "approved"}
                )
                if already >= order.total_cents:
                    order.status = "refunded"
                    order.payment_status = "refunded"
        else:
            refund.status = "denied"

        s.add(
            AuditLog(
                correlation_id=f"ops-{approval.id}",
                actor="ops:human",
                action="approval_decision",
                target=f"approval:{approval.id}",
                decision=approval.status.upper(),
                reason_code=payload.note or "human_review",
                detail=f"refund={refund.id} amount={refund.amount_cents}",
            )
        )
        s.commit()
        return {
            "approval_id": approval.id,
            "status": approval.status,
            "refund_status": refund.status,
        }


@app.get("/api/ops/escalations")
def escalations(_: None = Depends(_require_ops)) -> list[dict]:
    with next(get_session()) as s:
        rows = s.scalars(select(Escalation).order_by(Escalation.id.desc()).limit(50))
        return [
            {
                "id": e.id,
                "conversation_id": e.conversation_id,
                "reason": e.reason,
                "summary": e.summary,
                "status": e.status,
                "created_at": e.created_at.isoformat(),
            }
            for e in rows
        ]


@app.get("/api/ops/audit")
def audit(_: None = Depends(_require_ops)) -> list[dict]:
    with next(get_session()) as s:
        rows = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100))
        return [
            {
                "id": a.id,
                "ts": a.ts.isoformat(),
                "actor": a.actor,
                "action": a.action,
                "target": a.target,
                "decision": a.decision,
                "reason_code": a.reason_code,
                "correlation_id": a.correlation_id,
            }
            for a in rows
        ]


@app.get("/api/ops/stats")
def stats(_: None = Depends(_require_ops)) -> dict:
    with next(get_session()) as s:
        return {
            "orders": s.scalar(select(func.count()).select_from(Order)) or 0,
            "conversations": s.scalar(select(func.count()).select_from(Conversation)) or 0,
            "pending_approvals": s.scalar(
                select(func.count()).select_from(Approval).where(Approval.status == "pending")
            )
            or 0,
            "escalations": s.scalar(
                select(func.count()).select_from(Escalation).where(Escalation.status == "open")
            )
            or 0,
            "policy_version": settings.policy_version,
            "model_id": getattr(backend(), "model_id", "unknown"),
        }


# --- provenance + health ----------------------------------------------------


@app.get("/api/model-info")
def model_info() -> dict:
    return {
        "backend": settings.backend,
        "model_id": getattr(backend(), "model_id", "unknown"),
        "base_model": "Qwen/Qwen2.5-3B-Instruct",
        "serving": "GGUF Q4_K_M via llama.cpp (CPU)"
        if settings.backend == "llamacpp"
        else "rules baseline",
        "policy_version": settings.policy_version,
        "refund_approval_threshold_cents": settings.refund_approval_threshold_cents,
        "note": "Mock backend is the offline baseline, not the fine-tuned model.",
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "policy_version": settings.policy_version}


@app.get("/readyz")
def readyz() -> dict:
    with next(get_session()) as s:
        ok = bool(s.scalar(select(func.count()).select_from(Customer)))
    if not ok:
        raise HTTPException(status_code=503, detail="Database not seeded.")
    return {"status": "ready"}


@app.post("/api/sentiment/analyze")
def analyze_customer_sentiment(payload: MessageIn) -> dict:
    verdict = analyze_sentiment(payload.message)
    return {
        "label": verdict.label,
        "sentiment_score": verdict.sentiment_score,
        "urgency_score": verdict.urgency_score,
        "is_escalation_candidate": verdict.is_escalation_candidate,
        "triggers": verdict.triggers,
    }


@app.post("/api/feedback/csat")
def record_csat_feedback(feedback: CSATFeedback) -> dict:
    return {"status": "recorded", "feedback": feedback.model_dump()}


# --- pages ------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def chat_page() -> str:
    return CHAT_HTML


@app.get("/ops", response_class=HTMLResponse)
def ops_page() -> str:
    return OPS_HTML

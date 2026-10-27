"""Tool layer.

Every tool takes a server-side ToolContext. The model supplies only arguments, never
identity. Policy is re-evaluated inside each mutating tool, so a compromised or
confused model still cannot execute an ineligible action.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import policy
from .db import (
    Approval,
    AuditLog,
    Conversation,
    Customer,
    Escalation,
    IdempotencyKey,
    Order,
    OrderItem,
    Product,
    Refund,
    ReplacementRequest,
    ReturnLabel,
    ReturnRequest,
    Shipment,
    SopApproval,
    Ticket,
    TrackingEvent,
    Warranty,
)
from .retrieval import Retriever
from .schemas import ToolCall, ToolResult
from .sop import evaluate_authority


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolContext:
    session: Session
    customer_id: int
    conversation_id: int
    correlation_id: str
    retriever: Retriever
    now: datetime | None = None

    def clock(self) -> datetime:
        return self.now or datetime.utcnow()


# --- helpers ----------------------------------------------------------------


def _audit(
    ctx: ToolContext,
    action: str,
    target: str,
    decision: str,
    reason: str,
    detail: dict | None = None,
) -> None:
    ctx.session.add(
        AuditLog(
            correlation_id=ctx.correlation_id,
            actor=f"customer:{ctx.customer_id}",
            action=action,
            target=target,
            decision=decision,
            reason_code=reason,
            detail=json.dumps(detail or {}),
        )
    )


def _owned_order(ctx: ToolContext, order_id: str) -> Order:
    order = ctx.session.get(Order, order_id)
    # One message for both cases: prevents order-id enumeration.
    if order is None:
        _audit(ctx, "get_order", order_id, "DENY", "UNKNOWN_ORDER")
        ctx.session.commit()
        raise ToolError("UNKNOWN_ORDER", "I couldn't find that order on your account.")
    access = policy.evaluate_access(order.customer_id, ctx.customer_id)
    if not access.allowed:
        _audit(ctx, "get_order", order_id, "DENY", access.reason.value)
        ctx.session.commit()
        raise ToolError("NOT_OWNER", "I couldn't find that order on your account.")
    return order


def _prod(session: Session, sku: str) -> Product | None:
    return session.get(Product, sku)


def _items(session: Session, order_id: str) -> list[OrderItem]:
    return list(session.scalars(select(OrderItem).where(OrderItem.order_id == order_id)))


def _refund_summary(session: Session, order_id: str) -> tuple[int, list[dict]]:
    rows = list(session.scalars(select(Refund).where(Refund.order_id == order_id)))
    live = [r for r in rows if r.status in {"approved", "processed", "pending_approval"}]
    total = sum(r.amount_cents for r in live)
    return total, [
        {"id": r.id, "amount_cents": r.amount_cents, "status": r.status, "reason": r.reason}
        for r in rows
    ]


def _product_json(p: Product) -> dict:
    return {
        "sku": p.sku,
        "name": p.name,
        "category": p.category,
        "price_cents": p.price_cents,
        "description": p.description,
        "specs": json.loads(p.specs or "{}"),
        "final_sale": p.final_sale,
        "returnable": p.returnable,
        "warranty_months": p.warranty_months,
        "in_stock": p.in_stock,
    }


def _order_json(ctx: ToolContext, order: Order) -> dict:
    items = _items(ctx.session, order.id)
    refunded, refunds = _refund_summary(ctx.session, order.id)
    ship = ctx.session.scalar(
        select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.id.desc())
    )
    return {
        "order_id": order.id,
        "status": order.status,
        "placed_at": order.placed_at.isoformat(),
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "total_cents": order.total_cents,
        "payment_status": order.payment_status,
        "items": [
            {
                "sku": i.sku,
                "name": (_prod(ctx.session, i.sku).name if _prod(ctx.session, i.sku) else i.sku),
                "qty": i.qty,
                "unit_price_cents": i.unit_price_cents,
            }
            for i in items
        ],
        "shipment": (
            {
                "carrier": ship.carrier,
                "tracking": ship.tracking,
                "status": ship.status,
                "eta": ship.eta.isoformat() if ship.eta else None,
            }
            if ship
            else None
        ),
        "refunded_cents": refunded,
        "refundable_cents": max(0, order.total_cents - refunded),
        "refunds": refunds,
    }


def _idem_key(ctx: ToolContext, tool: str, payload: dict, explicit: str | None) -> str:
    scope = f"c{ctx.customer_id}"
    if explicit:
        return f"{scope}:{tool}:{explicit}"
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"{scope}:{tool}:{digest}"


def _dedupe(ctx: ToolContext, key: str) -> dict | None:
    row = ctx.session.scalar(select(IdempotencyKey).where(IdempotencyKey.key == key))
    if row is None:
        return None
    result = json.loads(row.result_json)
    result["deduplicated"] = True
    return result


def _remember(ctx: ToolContext, key: str, tool: str, result: dict) -> None:
    ctx.session.add(IdempotencyKey(key=key, tool=tool, result_json=json.dumps(result)))


def _replay_after_conflict(ctx: ToolContext, key: str) -> dict | None:
    """A concurrent twin may have won the unique-key race. Roll back and read its result.

    Returns the stored result (marked deduplicated) when it exists, otherwise ``None``.
    """
    ctx.session.rollback()
    return _dedupe(ctx, key)


def _flush_or_replay(ctx: ToolContext, key: str) -> dict | None:
    """Flush the pending mutation, mapping a unique-key collision to an idempotent replay."""
    try:
        ctx.session.flush()
    except IntegrityError:
        cached = _replay_after_conflict(ctx, key)
        if cached is not None:
            return cached
        raise
    return None


def _commit_or_replay(ctx: ToolContext, key: str) -> dict | None:
    """Commit, mapping a unique-key collision at commit time to an idempotent replay."""
    try:
        ctx.session.commit()
    except IntegrityError:
        cached = _replay_after_conflict(ctx, key)
        if cached is not None:
            return cached
        raise
    return None


# --- read tools -------------------------------------------------------------


def get_order(ctx: ToolContext, order_id: str) -> dict:
    return _order_json(ctx, _owned_order(ctx, order_id))


def get_shipment_status(ctx: ToolContext, order_id: str) -> dict:
    order = _owned_order(ctx, order_id)
    ship = ctx.session.scalar(
        select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.id.desc())
    )
    if ship is None:
        return {"order_id": order.id, "status": "not_shipped", "events": []}
    events = list(
        ctx.session.scalars(
            select(TrackingEvent)
            .where(TrackingEvent.shipment_id == ship.id)
            .order_by(TrackingEvent.ts)
        )
    )
    return {
        "order_id": order.id,
        "carrier": ship.carrier,
        "tracking": ship.tracking,
        "status": ship.status,
        "eta": ship.eta.isoformat() if ship.eta else None,
        "events": [
            {"ts": e.ts.isoformat(), "status": e.status, "location": e.location} for e in events
        ],
    }


def get_product_details(ctx: ToolContext, sku: str) -> dict:
    product = _prod(ctx.session, sku)
    if product is None:
        raise ToolError("UNKNOWN_PRODUCT", f"I don't have a product with the code {sku}.")
    return _product_json(product)


def search_product_catalog(ctx: ToolContext, query: str, limit: int = 5) -> dict:
    q = query.lower().strip()
    rows = list(ctx.session.scalars(select(Product)))
    hits = [
        _product_json(p)
        for p in rows
        if q in p.name.lower() or q in p.category.lower() or q in p.description.lower()
    ][: max(1, min(limit, 10))]
    return {"query": query, "results": hits, "count": len(hits)}


def search_help_center(ctx: ToolContext, query: str) -> dict:
    chunks = [c for c in ctx.retriever.search(query, k=6) if c.doc_id.startswith(("help", "faq"))][
        :4
    ]
    return {
        "query": query,
        "results": [{"doc_id": c.doc_id, "title": c.title, "text": c.text} for c in chunks],
        "count": len(chunks),
    }


def retrieve_policy(ctx: ToolContext, query: str) -> dict:
    chunks = [c for c in ctx.retriever.search(query, k=6) if c.doc_id.startswith("pol")][:4]
    return {
        "query": query,
        "results": [
            {"doc_id": c.doc_id, "title": c.title, "text": c.text, "version": c.version}
            for c in chunks
        ],
        "count": len(chunks),
    }


def check_warranty(ctx: ToolContext, order_id: str, sku: str) -> dict:
    order = _owned_order(ctx, order_id)
    warranty = ctx.session.scalar(
        select(Warranty).where(Warranty.order_id == order.id, Warranty.sku == sku)
    )
    if warranty is None:
        raise ToolError("NO_WARRANTY", "I don't see a warranty record for that item on this order.")
    verdict = policy.evaluate_warranty(expires_at=warranty.expires_at, now=ctx.clock())
    return {
        "order_id": order.id,
        "sku": sku,
        "decision": verdict.decision.value,
        "reason_code": verdict.reason.value,
        "explanation": verdict.explanation,
        "expires_at": warranty.expires_at.isoformat(),
    }


def get_refund_status(ctx: ToolContext, order_id: str) -> dict:
    order = _owned_order(ctx, order_id)
    refunded, refunds = _refund_summary(ctx.session, order.id)
    return {
        "order_id": order.id,
        "refunded_cents": refunded,
        "refundable_cents": max(0, order.total_cents - refunded),
        "refunds": refunds,
    }


def check_return_eligibility(
    ctx: ToolContext, order_id: str, sku: str, reason_code: str, quantity: int = 1
) -> dict:
    order = _owned_order(ctx, order_id)
    item = next((i for i in _items(ctx.session, order.id) if i.sku == sku), None)
    if item is None:
        raise ToolError("SKU_NOT_IN_ORDER", "That item isn't part of this order.")
    product = _prod(ctx.session, sku)
    if product is None:
        raise ToolError("UNKNOWN_PRODUCT", "I couldn't load that product.")
    verdict = policy.evaluate_return(
        delivered_at=order.delivered_at,
        reason_code=reason_code,
        product_final_sale=product.final_sale,
        product_returnable=product.returnable,
        now=ctx.clock(),
    )
    return {
        "order_id": order.id,
        "sku": sku,
        "quantity": quantity,
        "decision": verdict.decision.value,
        "reason_code": verdict.reason.value,
        "explanation": verdict.explanation,
        "return_by": (
            policy.next_return_window_end(order.delivered_at).date().isoformat()  # type: ignore[union-attr]
            if policy.next_return_window_end(order.delivered_at)
            else None
        ),
    }


# --- state-changing tools ---------------------------------------------------


def create_return_request(
    ctx: ToolContext,
    order_id: str,
    sku: str,
    reason_code: str,
    quantity: int = 1,
    idempotency_key: str | None = None,
) -> dict:
    order = _owned_order(ctx, order_id)
    item = next((i for i in _items(ctx.session, order.id) if i.sku == sku), None)
    product = _prod(ctx.session, sku)
    if item is None or product is None:
        raise ToolError("SKU_NOT_IN_ORDER", "That item isn't part of this order.")

    verdict = policy.evaluate_return(
        delivered_at=order.delivered_at,
        reason_code=reason_code,
        product_final_sale=product.final_sale,
        product_returnable=product.returnable,
        now=ctx.clock(),
    )
    if not verdict.allowed:
        _audit(ctx, "create_return_request", f"{order.id}/{sku}", "DENY", verdict.reason.value)
        ctx.session.commit()  # persist the denial audit trail
        raise ToolError(verdict.reason.value, verdict.explanation)

    key = _idem_key(
        ctx, "create_return_request", {"o": order.id, "s": sku, "r": reason_code}, idempotency_key
    )
    if (cached := _dedupe(ctx, key)) is not None:
        return cached

    req = ReturnRequest(
        order_id=order.id,
        sku=sku,
        qty=max(1, min(quantity, item.qty)),
        reason=reason_code,
        status="created",
        idempotency_key=key,
    )
    ctx.session.add(req)
    ctx.session.flush()
    label = ReturnLabel(
        return_request_id=req.id,
        code=f"RMA-{uuid.uuid4().hex[:8].upper()}",
        expires_at=ctx.clock() + timedelta(days=14),
    )
    ctx.session.add(label)
    result = {
        "return_request_id": req.id,
        "order_id": order.id,
        "sku": sku,
        "status": "created",
        "label_code": label.code,
        "label_expires_at": label.expires_at.isoformat(),
        "instructions": "Print the prepaid label and drop the parcel at any MockPost counter.",
    }
    _remember(ctx, key, "create_return_request", result)
    _audit(ctx, "create_return_request", f"{order.id}/{sku}", "ALLOW", "OK", result)
    ctx.session.commit()
    return result


def create_replacement_request(
    ctx: ToolContext,
    order_id: str,
    sku: str,
    reason_code: str,
    quantity: int = 1,
    idempotency_key: str | None = None,
) -> dict:
    order = _owned_order(ctx, order_id)
    item = next((i for i in _items(ctx.session, order.id) if i.sku == sku), None)
    product = _prod(ctx.session, sku)
    if item is None or product is None:
        raise ToolError("SKU_NOT_IN_ORDER", "That item isn't part of this order.")

    verdict = policy.evaluate_replacement(
        delivered_at=order.delivered_at,
        reason_code=reason_code,
        product_final_sale=product.final_sale,
        now=ctx.clock(),
    )
    if not verdict.allowed:
        _audit(ctx, "create_replacement_request", f"{order.id}/{sku}", "DENY", verdict.reason.value)
        ctx.session.commit()  # persist the denial audit trail
        raise ToolError(verdict.reason.value, verdict.explanation)

    key = _idem_key(
        ctx,
        "create_replacement_request",
        {"o": order.id, "s": sku, "r": reason_code},
        idempotency_key,
    )
    if (cached := _dedupe(ctx, key)) is not None:
        return cached

    req = ReplacementRequest(
        order_id=order.id,
        sku=sku,
        qty=max(1, min(quantity, item.qty)),
        reason=reason_code,
        status="created",
        idempotency_key=key,
    )
    ctx.session.add(req)
    if (cached := _flush_or_replay(ctx, key)) is not None:
        return cached
    result = {
        "replacement_request_id": req.id,
        "order_id": order.id,
        "sku": sku,
        "status": "created",
        "eta_days": 3,
    }
    _remember(ctx, key, "create_replacement_request", result)
    _audit(ctx, "create_replacement_request", f"{order.id}/{sku}", "ALLOW", "OK", result)
    if (cached := _commit_or_replay(ctx, key)) is not None:
        return cached
    return result


def request_cancellation(
    ctx: ToolContext,
    order_id: str,
    reason: str = "customer_request",
    idempotency_key: str | None = None,
) -> dict:
    order = _owned_order(ctx, order_id)
    verdict = policy.evaluate_cancellation(order_status=order.status)
    if not verdict.allowed:
        _audit(ctx, "request_cancellation", order.id, "DENY", verdict.reason.value)
        ctx.session.commit()  # persist the denial audit trail
        raise ToolError(verdict.reason.value, verdict.explanation)

    key = _idem_key(ctx, "request_cancellation", {"o": order.id}, idempotency_key)
    if (cached := _dedupe(ctx, key)) is not None:
        return cached

    order.status = "cancelled"
    if (cached := _flush_or_replay(ctx, key)) is not None:
        return cached
    refund = Refund(
        order_id=order.id,
        amount_cents=order.total_cents,
        status="processed",
        reason="cancellation",
        idempotency_key=f"{key}:refund",
    )
    ctx.session.add(refund)
    if (cached := _flush_or_replay(ctx, key)) is not None:
        return cached
    order.payment_status = "refunded"
    result = {
        "order_id": order.id,
        "status": "cancelled",
        "refund_id": refund.id,
        "refund_amount_cents": order.total_cents,
        "refund_status": "processed",
    }
    _remember(ctx, key, "request_cancellation", result)
    _audit(ctx, "request_cancellation", order.id, "ALLOW", "OK", result)
    if (cached := _commit_or_replay(ctx, key)) is not None:
        return cached
    return result


def submit_refund_request(
    ctx: ToolContext,
    order_id: str,
    reason_code: str,
    sku: str | None = None,
    quantity: int | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Amount is computed server-side. The model can never name a refund figure."""
    order = _owned_order(ctx, order_id)
    items = _items(ctx.session, order.id)
    distinct = {i.sku for i in items}

    if sku is None and len(distinct) > 1:
        raise ToolError(
            "MISSING_ITEM",
            "Which item should be refunded — the order has multiple products?",
        )
    target_sku = sku or (items[0].sku if items else None)
    if target_sku is None:
        raise ToolError("EMPTY_ORDER", "That order has no items to refund.")

    item = next((i for i in items if i.sku == target_sku), None)
    product = _prod(ctx.session, target_sku)
    if item is None or product is None:
        raise ToolError("SKU_NOT_IN_ORDER", "That item isn't part of this order.")

    qty = max(1, min(quantity or item.qty, item.qty))
    amount = item.unit_price_cents * qty
    refunded, _ = _refund_summary(ctx.session, order.id)
    recent = ctx.session.scalar(
        select(Refund).where(
            Refund.order_id == order.id, Refund.created_at >= ctx.clock() - timedelta(days=30)
        )
    )
    refunds_last_30d = 1 if recent else 0

    # Idempotent replay must return the original result, before policy is re-evaluated:
    # after the first refund the balance is smaller, but the request is the same request.
    key = _idem_key(
        ctx,
        "submit_refund_request",
        {"o": order.id, "s": target_sku, "r": reason_code},
        idempotency_key,
    )
    if (cached := _dedupe(ctx, key)) is not None:
        return cached

    verdict = policy.evaluate_refund(
        order_total_cents=order.total_cents,
        already_refunded_cents=refunded,
        amount_cents=amount,
        delivered_at=order.delivered_at,
        reason_code=reason_code,
        product_final_sale=product.final_sale,
        product_returnable=product.returnable,
        refunds_last_30d=refunds_last_30d,
        now=ctx.clock(),
    )

    if verdict.decision is policy.Decision.DENY:
        _audit(
            ctx, "submit_refund_request", f"{order.id}/{target_sku}", "DENY", verdict.reason.value
        )
        ctx.session.commit()  # persist the denial audit trail
        raise ToolError(verdict.reason.value, verdict.explanation)

    if verdict.decision in {policy.Decision.REQUIRE_APPROVAL, policy.Decision.ESCALATE}:
        refund = Refund(
            order_id=order.id,
            amount_cents=amount,
            status="pending_approval",
            reason=reason_code,
            idempotency_key=key,
        )
        ctx.session.add(refund)
        if (cached := _flush_or_replay(ctx, key)) is not None:
            return cached
        approval = Approval(
            conversation_id=ctx.conversation_id,
            refund_id=refund.id,
            amount_cents=amount,
            reason=f"{verdict.reason.value}: {verdict.explanation}",
            status="pending",
        )
        ctx.session.add(approval)

        # ── SOP row for the ops panel ──
        sop_v = evaluate_authority(amount)
        approval.sop_tier = sop_v.tier_number
        approval.required_role = sop_v.required_label
        cust = ctx.session.get(Customer, ctx.customer_id)
        customer_name = cust.name if cust else "unknown"
        sop_row = SopApproval(
            approval_id=approval.id,
            order_id=order.id,
            customer_name=customer_name,
            action_type="refund",
            amount_cents=amount,
            reason_code=reason_code,
            sop_tier=sop_v.tier_number,
            required_role=sop_v.required_label,
            status="pending",
        )
        ctx.session.add(sop_row)

        escalation = Escalation(
            conversation_id=ctx.conversation_id,
            reason=verdict.reason.value,
            summary=f"Refund {amount} on {order.id} needs review: {verdict.explanation}",
            status="open",
        )
        ctx.session.add(escalation)
        result = {
            "order_id": order.id,
            "sku": target_sku,
            "amount_cents": amount,
            "status": "pending_approval",
            "refund_id": refund.id,
            "approval_id": approval.id,
            "escalation_id": escalation.id,
            "reason_code": verdict.reason.value,
            "explanation": verdict.explanation,
            "sop_tier": sop_v.tier_number,
            "sop_required_role": sop_v.required_label,
        }
        _remember(ctx, key, "submit_refund_request", result)
        _audit(
            ctx, "submit_refund_request", order.id, "REQUIRE_APPROVAL", verdict.reason.value, result
        )
        if (cached := _commit_or_replay(ctx, key)) is not None:
            return cached
        return result

    key = _idem_key(
        ctx,
        "submit_refund_request",
        {"o": order.id, "s": target_sku, "r": reason_code},
        idempotency_key,
    )

    refund = Refund(
        order_id=order.id,
        amount_cents=amount,
        status="processed",
        reason=reason_code,
        idempotency_key=key,
    )
    ctx.session.add(refund)
    if (cached := _flush_or_replay(ctx, key)) is not None:
        return cached
    if refunded + amount >= order.total_cents:
        order.status = "refunded"
        order.payment_status = "refunded"
    result = {
        "order_id": order.id,
        "sku": target_sku,
        "amount_cents": amount,
        "status": "processed",
        "refund_id": refund.id,
        "reason_code": "OK",
    }
    _remember(ctx, key, "submit_refund_request", result)
    _audit(ctx, "submit_refund_request", order.id, "ALLOW", "OK", result)
    if (cached := _commit_or_replay(ctx, key)) is not None:
        return cached
    return result


def create_support_ticket(ctx: ToolContext, subject: str, body: str = "") -> dict:
    ticket = Ticket(
        customer_id=ctx.customer_id,
        subject=subject[:200],
        status="open",
        channel="chat",
    )
    ctx.session.add(ticket)
    ctx.session.flush()
    result = {"ticket_id": ticket.id, "status": "open", "subject": ticket.subject}
    _audit(ctx, "create_support_ticket", f"ticket:{ticket.id}", "ALLOW", "OK", result)
    ctx.session.commit()
    return result


def escalate_to_human(ctx: ToolContext, reason: str, summary: str = "") -> dict:
    esc = Escalation(
        conversation_id=ctx.conversation_id,
        reason=reason[:240],
        summary=summary[:4000],
        status="open",
    )
    ctx.session.add(esc)
    ctx.session.flush()
    conv = ctx.session.get(Conversation, ctx.conversation_id)
    if conv is not None:
        conv.status = "escalated"
    result = {"escalation_id": esc.id, "status": "open", "case_reference": f"ESC-{esc.id:05d}"}
    _audit(
        ctx, "escalate_to_human", f"conversation:{ctx.conversation_id}", "ESCALATE", reason, result
    )
    ctx.session.commit()
    return result


# --- registry ---------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[..., dict]
    read_only: bool


REGISTRY: dict[str, ToolSpec] = {
    "get_order": ToolSpec("get_order", get_order, True),
    "get_shipment_status": ToolSpec("get_shipment_status", get_shipment_status, True),
    "get_product_details": ToolSpec("get_product_details", get_product_details, True),
    "search_product_catalog": ToolSpec("search_product_catalog", search_product_catalog, True),
    "search_help_center": ToolSpec("search_help_center", search_help_center, True),
    "retrieve_policy": ToolSpec("retrieve_policy", retrieve_policy, True),
    "check_warranty": ToolSpec("check_warranty", check_warranty, True),
    "get_refund_status": ToolSpec("get_refund_status", get_refund_status, True),
    "check_return_eligibility": ToolSpec(
        "check_return_eligibility", check_return_eligibility, True
    ),
    "create_return_request": ToolSpec("create_return_request", create_return_request, False),
    "create_replacement_request": ToolSpec(
        "create_replacement_request", create_replacement_request, False
    ),
    "request_cancellation": ToolSpec("request_cancellation", request_cancellation, False),
    "submit_refund_request": ToolSpec("submit_refund_request", submit_refund_request, False),
    "create_support_ticket": ToolSpec("create_support_ticket", create_support_ticket, False),
    "escalate_to_human": ToolSpec("escalate_to_human", escalate_to_human, False),
}


def execute_tool(ctx: ToolContext, call: ToolCall) -> ToolResult:
    """Validate arguments against the handler signature, then run. Never coerces types."""
    spec = REGISTRY.get(call.name)
    if spec is None:
        return ToolResult(tool=call.name, ok=False, error="UNKNOWN_TOOL")

    sig = inspect.signature(spec.handler)
    params = {k: v for k, v in sig.parameters.items() if k != "ctx"}
    allowed = set(params)
    extra = set(call.arguments) - allowed
    if extra:
        return ToolResult(
            tool=call.name, ok=False, error=f"UNEXPECTED_ARGS:{','.join(sorted(extra))}"
        )

    missing = [
        name
        for name, p in params.items()
        if p.default is inspect.Parameter.empty and name not in call.arguments
    ]
    if missing:
        return ToolResult(tool=call.name, ok=False, error=f"MISSING_ARGS:{','.join(missing)}")

    try:
        data = spec.handler(ctx, **call.arguments)
        return ToolResult(tool=call.name, ok=True, data=data, trace_id=ctx.correlation_id)
    except ToolError as exc:
        return ToolResult(tool=call.name, ok=False, error=exc.code, data={"message": exc.message})
    except Exception as exc:  # noqa: BLE001 - converted to a structured tool failure
        ctx.session.rollback()
        return ToolResult(
            tool=call.name,
            ok=False,
            error="TOOL_FAILURE",
            data={"message": "Something went wrong on our side.", "detail": type(exc).__name__},
        )

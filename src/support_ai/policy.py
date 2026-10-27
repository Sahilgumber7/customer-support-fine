"""Deterministic policy engine.

The model proposes; this module decides. Every function is pure: it takes explicit
facts and returns a Verdict. No LLM output can widen a decision here, and no function
mutates state. Tools call these *before* executing anything, then re-check.

SOP integration: evaluate_refund_with_sop() returns both a Verdict *and* the
SopVerdict so the orchestrator can route approvals to the correct authority tier
without any LLM involvement in that decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .config import settings
from .sop import SopVerdict, evaluate_authority


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_INFORMATION = "REQUIRE_INFORMATION"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    ESCALATE = "ESCALATE"


class Reason(str, Enum):
    OK = "OK"
    NOT_OWNER = "NOT_OWNER"
    UNKNOWN_ORDER = "UNKNOWN_ORDER"
    OUT_OF_WINDOW = "OUT_OF_WINDOW"
    FINAL_SALE = "FINAL_SALE"
    NOT_RETURNABLE = "NOT_RETURNABLE"
    NOT_YET_DELIVERED = "NOT_YET_DELIVERED"
    ALREADY_SHIPPED = "ALREADY_SHIPPED"
    ALREADY_CANCELLED = "ALREADY_CANCELLED"
    ALREADY_REFUNDED = "ALREADY_REFUNDED"
    OVER_THRESHOLD = "OVER_THRESHOLD"
    HIGH_RISK = "HIGH_RISK"
    SKU_NOT_IN_ORDER = "SKU_NOT_IN_ORDER"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    WARRANTY_EXPIRED = "WARRANTY_EXPIRED"
    WARRANTY_ACTIVE = "WARRANTY_ACTIVE"
    MISSING_INFO = "MISSING_INFO"
    SUSPECTED_ABUSE = "SUSPECTED_ABUSE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: Reason
    explanation: str
    requires_approval: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


def _allow(reason: Reason, why: str) -> Verdict:
    return Verdict(Decision.ALLOW, reason, why)


def _deny(reason: Reason, why: str) -> Verdict:
    return Verdict(Decision.DENY, reason, why)


def _need_info(why: str) -> Verdict:
    return Verdict(Decision.REQUIRE_INFORMATION, Reason.MISSING_INFO, why)


# --- access -----------------------------------------------------------------


def evaluate_access(order_customer_id: int, session_customer_id: int) -> Verdict:
    """Order ownership. Session identity comes from the server, never the model."""
    if order_customer_id != session_customer_id:
        return _deny(Reason.NOT_OWNER, "This order does not belong to the authenticated customer.")
    return _allow(Reason.OK, "Ownership verified.")


# --- returns ----------------------------------------------------------------

DEFECT_REASONS = {
    "damaged",
    "defective",
    "broken",
    "wrong_item",
    "missing_item",
    "not_as_described",
}


def _window_days(reason_code: str) -> int:
    return (
        settings.defective_return_window_days
        if reason_code in DEFECT_REASONS
        else settings.return_window_days
    )


def evaluate_return(
    *,
    delivered_at: datetime | None,
    reason_code: str,
    product_final_sale: bool,
    product_returnable: bool,
    now: datetime | None = None,
) -> Verdict:
    if delivered_at is None:
        return _deny(Reason.NOT_YET_DELIVERED, "The order has not been delivered yet.")
    now = now or datetime.utcnow()
    days = (now - delivered_at).days
    window = _window_days(reason_code)
    if days > window:
        return _deny(
            Reason.OUT_OF_WINDOW,
            f"Return window is {window} days; this order was delivered {days} days ago.",
        )
    if not product_returnable:
        return _deny(Reason.NOT_RETURNABLE, "This item is marked non-returnable.")
    if product_final_sale and reason_code not in DEFECT_REASONS:
        return _deny(
            Reason.FINAL_SALE,
            "Final-sale items are only returnable if damaged, defective, or not as described.",
        )
    return _allow(Reason.OK, f"Within the {window}-day window and eligible for return.")


def evaluate_replacement(
    *,
    delivered_at: datetime | None,
    reason_code: str,
    product_final_sale: bool,
    now: datetime | None = None,
) -> Verdict:
    """Replacements are for defects; final-sale still qualifies when defective."""
    if delivered_at is None:
        return _deny(Reason.NOT_YET_DELIVERED, "The order has not been delivered yet.")
    if reason_code not in DEFECT_REASONS:
        return _deny(
            Reason.INVALID_AMOUNT,
            "Replacements are issued for damaged, defective, wrong, or missing items only.",
        )
    now = now or datetime.utcnow()
    days = (now - delivered_at).days
    window = settings.defective_return_window_days
    if days > window:
        return _deny(
            Reason.OUT_OF_WINDOW,
            f"Replacement window is {window} days; this order was delivered {days} days ago.",
        )
    return _allow(Reason.OK, "Defect reported within the replacement window.")


# --- cancellation -----------------------------------------------------------


def evaluate_cancellation(*, order_status: str) -> Verdict:
    if order_status == "cancelled":
        return _deny(Reason.ALREADY_CANCELLED, "This order is already cancelled.")
    if order_status in {"shipped", "delivered", "refunded"}:
        return _deny(
            Reason.ALREADY_SHIPPED,
            "The order has already shipped; use the return flow instead of cancelling.",
        )
    return _allow(Reason.OK, "Order has not shipped and can be cancelled.")


# --- refunds ----------------------------------------------------------------


def evaluate_refund(
    *,
    order_total_cents: int,
    already_refunded_cents: int,
    amount_cents: int,
    delivered_at: datetime | None,
    reason_code: str,
    product_final_sale: bool,
    product_returnable: bool,
    refunds_last_30d: int = 0,
    now: datetime | None = None,
) -> Verdict:
    if amount_cents <= 0:
        return _deny(Reason.INVALID_AMOUNT, "Refund amount must be positive.")
    remaining = order_total_cents - already_refunded_cents
    if remaining <= 0:
        return _deny(Reason.ALREADY_REFUNDED, "This order has already been fully refunded.")
    if amount_cents > remaining:
        return _deny(
            Reason.INVALID_AMOUNT,
            f"Refund of {amount_cents} exceeds the remaining refundable balance of {remaining}.",
        )

    base = evaluate_return(
        delivered_at=delivered_at,
        reason_code=reason_code,
        product_final_sale=product_final_sale,
        product_returnable=product_returnable,
        now=now,
    )
    if not base.allowed:
        return base

    if refunds_last_30d >= 3:
        return Verdict(
            Decision.ESCALATE,
            Reason.SUSPECTED_ABUSE,
            "Multiple refunds recently; requires human review.",
        )
    # Use SOP tier to decide auto-approve vs. which authority must sign off.
    sop = evaluate_authority(amount_cents)
    if sop.auto_approve:
        return _allow(Reason.OK, f"Refund of ${amount_cents/100:.2f} is within auto-approval limit.")
    return Verdict(
        Decision.REQUIRE_APPROVAL,
        Reason.OVER_THRESHOLD,
        f"Refund of ${amount_cents/100:.2f} requires approval by a {sop.required_label} (SOP Tier {sop.tier_number}).",
        requires_approval=True,
    )


@dataclass(frozen=True)
class RefundWithSop:
    verdict: Verdict
    sop: SopVerdict


def evaluate_refund_with_sop(
    *,
    order_total_cents: int,
    already_refunded_cents: int,
    amount_cents: int,
    delivered_at: datetime | None,
    reason_code: str,
    product_final_sale: bool,
    product_returnable: bool,
    refunds_last_30d: int = 0,
    now: datetime | None = None,
) -> RefundWithSop:
    """Same as evaluate_refund but also returns the SOP tier verdict."""
    verdict = evaluate_refund(
        order_total_cents=order_total_cents,
        already_refunded_cents=already_refunded_cents,
        amount_cents=amount_cents,
        delivered_at=delivered_at,
        reason_code=reason_code,
        product_final_sale=product_final_sale,
        product_returnable=product_returnable,
        refunds_last_30d=refunds_last_30d,
        now=now,
    )
    sop = evaluate_authority(max(amount_cents, 1))
    return RefundWithSop(verdict=verdict, sop=sop)


# --- warranty ---------------------------------------------------------------


def evaluate_warranty(*, expires_at: datetime | None, now: datetime | None = None) -> Verdict:
    now = now or datetime.utcnow()
    if expires_at is None:
        return Verdict(
            Decision.REQUIRE_INFORMATION, Reason.MISSING_INFO, "No warranty record for this item."
        )
    if expires_at < now:
        return _deny(
            Reason.WARRANTY_EXPIRED,
            f"Warranty expired on {expires_at.date().isoformat()}.",
        )
    return _allow(
        Reason.WARRANTY_ACTIVE, f"Warranty is active until {expires_at.date().isoformat()}."
    )


# --- escalation -------------------------------------------------------------


def evaluate_escalation(*, reason: str, tool_failures: int = 0, confidence: float = 1.0) -> Verdict:
    if tool_failures >= 2:
        return Verdict(
            Decision.ESCALATE,
            Reason.LOW_CONFIDENCE,
            "Repeated backend failures; escalating to a human.",
        )
    if confidence < 0.55:
        return Verdict(
            Decision.ESCALATE, Reason.LOW_CONFIDENCE, "Model confidence too low to act safely."
        )
    return Verdict(Decision.ESCALATE, Reason.MISSING_INFO, f"Escalated: {reason}")


def next_return_window_end(delivered_at: datetime | None) -> datetime | None:
    if delivered_at is None:
        return None
    return delivered_at + timedelta(days=settings.return_window_days)

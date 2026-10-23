"""Policy engine tests: pure functions, no LLM, no database."""

from datetime import datetime, timedelta

from support_ai import policy
from support_ai.policy import Decision, Reason

NOW = datetime(2026, 6, 1, 12, 0, 0)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


class TestReturns:
    def test_inside_standard_window(self):
        v = policy.evaluate_return(
            delivered_at=days_ago(5),
            reason_code="changed_mind",
            product_final_sale=False,
            product_returnable=True,
            now=NOW,
        )
        assert v.decision is Decision.ALLOW

    def test_outside_standard_window(self):
        v = policy.evaluate_return(
            delivered_at=days_ago(40),
            reason_code="changed_mind",
            product_final_sale=False,
            product_returnable=True,
            now=NOW,
        )
        assert v.decision is Decision.DENY
        assert v.reason is Reason.OUT_OF_WINDOW

    def test_defective_window_is_longer(self):
        v = policy.evaluate_return(
            delivered_at=days_ago(40),
            reason_code="defective",
            product_final_sale=False,
            product_returnable=True,
            now=NOW,
        )
        assert v.decision is Decision.ALLOW

    def test_defect_beyond_ninety_days(self):
        v = policy.evaluate_return(
            delivered_at=days_ago(95),
            reason_code="damaged",
            product_final_sale=False,
            product_returnable=True,
            now=NOW,
        )
        assert v.decision is Decision.DENY
        assert v.reason is Reason.OUT_OF_WINDOW

    def test_final_sale_change_of_mind_denied(self):
        v = policy.evaluate_return(
            delivered_at=days_ago(3),
            reason_code="changed_mind",
            product_final_sale=True,
            product_returnable=True,
            now=NOW,
        )
        assert v.decision is Decision.DENY
        assert v.reason is Reason.FINAL_SALE

    def test_final_sale_defect_allowed(self):
        v = policy.evaluate_return(
            delivered_at=days_ago(3),
            reason_code="damaged",
            product_final_sale=True,
            product_returnable=True,
            now=NOW,
        )
        assert v.decision is Decision.ALLOW

    def test_non_returnable(self):
        v = policy.evaluate_return(
            delivered_at=days_ago(3),
            reason_code="changed_mind",
            product_final_sale=False,
            product_returnable=False,
            now=NOW,
        )
        assert v.reason is Reason.NOT_RETURNABLE

    def test_not_delivered(self):
        v = policy.evaluate_return(
            delivered_at=None,
            reason_code="changed_mind",
            product_final_sale=False,
            product_returnable=True,
            now=NOW,
        )
        assert v.reason is Reason.NOT_YET_DELIVERED


class TestRefunds:
    BASE = dict(
        delivered_at=days_ago(5),
        reason_code="damaged",
        product_final_sale=False,
        product_returnable=True,
        refunds_last_30d=0,
    )

    def test_small_refund_allowed(self):
        v = policy.evaluate_refund(
            order_total_cents=12900,
            already_refunded_cents=0,
            amount_cents=12900,
            now=NOW,
            **self.BASE,
        )
        assert v.decision is Decision.ALLOW

    def test_over_threshold_requires_approval(self):
        v = policy.evaluate_refund(
            order_total_cents=19900,
            already_refunded_cents=0,
            amount_cents=19900,
            now=NOW,
            **self.BASE,
        )
        assert v.decision is Decision.REQUIRE_APPROVAL
        assert v.requires_approval

    def test_high_value_escalates(self):
        v = policy.evaluate_refund(
            order_total_cents=60000,
            already_refunded_cents=0,
            amount_cents=60000,
            now=NOW,
            **self.BASE,
        )
        assert v.decision is Decision.ESCALATE
        assert v.reason is Reason.HIGH_RISK

    def test_already_fully_refunded(self):
        v = policy.evaluate_refund(
            order_total_cents=9900,
            already_refunded_cents=9900,
            amount_cents=1000,
            now=NOW,
            **self.BASE,
        )
        assert v.reason is Reason.ALREADY_REFUNDED

    def test_amount_cannot_exceed_remaining(self):
        v = policy.evaluate_refund(
            order_total_cents=9900,
            already_refunded_cents=5000,
            amount_cents=6000,
            now=NOW,
            **self.BASE,
        )
        assert v.reason is Reason.INVALID_AMOUNT

    def test_repeated_refunds_escalate(self):
        v = policy.evaluate_refund(
            order_total_cents=20000,
            already_refunded_cents=0,
            amount_cents=5000,
            refunds_last_30d=3,
            delivered_at=days_ago(5),
            reason_code="damaged",
            product_final_sale=False,
            product_returnable=True,
            now=NOW,
        )
        assert v.decision is Decision.ESCALATE
        assert v.reason is Reason.SUSPECTED_ABUSE


class TestCancellation:
    def test_placed_can_cancel(self):
        assert policy.evaluate_cancellation(order_status="placed").allowed

    def test_shipped_cannot_cancel(self):
        v = policy.evaluate_cancellation(order_status="shipped")
        assert v.reason is Reason.ALREADY_SHIPPED

    def test_delivered_cannot_cancel(self):
        assert (
            policy.evaluate_cancellation(order_status="delivered").reason is Reason.ALREADY_SHIPPED
        )

    def test_already_cancelled(self):
        assert (
            policy.evaluate_cancellation(order_status="cancelled").reason
            is Reason.ALREADY_CANCELLED
        )


class TestWarrantyAndAccess:
    def test_active_warranty(self):
        assert policy.evaluate_warranty(expires_at=NOW + timedelta(days=30), now=NOW).allowed

    def test_expired_warranty(self):
        v = policy.evaluate_warranty(expires_at=NOW - timedelta(days=1), now=NOW)
        assert v.reason is Reason.WARRANTY_EXPIRED

    def test_no_warranty_record(self):
        v = policy.evaluate_warranty(expires_at=None, now=NOW)
        assert v.decision is Decision.REQUIRE_INFORMATION

    def test_ownership(self):
        assert policy.evaluate_access(1, 1).allowed
        assert policy.evaluate_access(1, 2).reason is Reason.NOT_OWNER

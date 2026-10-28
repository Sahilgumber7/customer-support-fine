"""Tool-layer tests: authorisation, argument validation, policy gating, idempotency.

These run without any LLM. If a tool cannot be made safe here, no model can rescue it.
"""

from sqlalchemy import func, select

from support_ai.db import Approval, Order, Refund, ReplacementRequest, ReturnLabel, ReturnRequest
from support_ai.schemas import ToolCall
from support_ai.tools import ToolContext, execute_tool


def call(ctx: ToolContext, name: str, **args):
    return execute_tool(ctx, ToolCall(name=name, arguments=args))


# --- authorisation ----------------------------------------------------------


def test_cannot_read_another_customers_order(ctx):
    result = call(ctx, "get_order", order_id="ORD-2001")
    assert not result.ok
    assert result.error == "NOT_OWNER"
    assert "items" not in result.data
    assert "total_cents" not in result.data


def test_unknown_and_foreign_orders_are_indistinguishable(ctx):
    foreign = call(ctx, "get_order", order_id="ORD-2001")
    unknown = call(ctx, "get_order", order_id="ORD-9999")
    assert foreign.error == "NOT_OWNER"
    assert unknown.error == "UNKNOWN_ORDER"
    assert foreign.data["message"] == unknown.data["message"]


def test_cannot_mutate_another_customers_order(ctx):
    before = ctx.session.get(Order, "ORD-2001").status
    refunds_before = ctx.session.scalar(select(func.count()).select_from(Refund))
    result = call(
        ctx, "submit_refund_request", order_id="ORD-2001", reason_code="damaged", sku="SKU-HDP-01"
    )
    assert not result.ok
    assert result.error == "NOT_OWNER"
    assert ctx.session.get(Order, "ORD-2001").status == before
    assert ctx.session.scalar(select(func.count()).select_from(Refund)) == refunds_before


def test_unknown_tool_rejected(ctx):
    result = call(ctx, "drop_all_tables")
    assert not result.ok
    assert result.error == "UNKNOWN_TOOL"


def test_extra_arguments_rejected(ctx):
    """A model cannot smuggle an amount, customer id, or override into a tool call."""
    result = call(
        ctx,
        "submit_refund_request",
        order_id="ORD-1001",
        reason_code="damaged",
        sku="SKU-HDP-01",
        amount_cents=999999,
    )
    assert not result.ok
    assert result.error.startswith("UNEXPECTED_ARGS")


def test_missing_arguments_rejected(ctx):
    result = call(ctx, "get_order")
    assert not result.ok
    assert result.error.startswith("MISSING_ARGS")


# --- refunds ----------------------------------------------------------------


def test_refund_computes_amount_server_side(ctx):
    result = call(
        ctx, "submit_refund_request", order_id="ORD-1001", reason_code="damaged", sku="SKU-HDP-01"
    )
    assert result.ok
    assert result.data["amount_cents"] == 12900
    assert result.data["status"] == "processed"
    refund = ctx.session.get(Refund, result.data["refund_id"])
    assert refund.amount_cents == 12900


def test_duplicate_submit_is_idempotent(ctx):
    payload = dict(order_id="ORD-1001", reason_code="damaged", sku="SKU-HDP-01")
    first = call(ctx, "submit_refund_request", **payload)
    second = call(ctx, "submit_refund_request", **payload)
    assert first.ok and second.ok
    assert second.data.get("deduplicated") is True
    assert first.data["refund_id"] == second.data["refund_id"]
    assert (
        ctx.session.scalar(
            select(func.count()).select_from(Refund).where(Refund.order_id == "ORD-1001")
        )
        == 1
    )


def test_out_of_window_refund_denied(ctx):
    before = ctx.session.scalar(select(func.count()).select_from(Refund))
    result = call(
        ctx,
        "submit_refund_request",
        order_id="ORD-1002",
        reason_code="changed_mind",
        sku="SKU-SHO-01",
    )
    assert not result.ok
    assert result.error == "OUT_OF_WINDOW"
    assert ctx.session.scalar(select(func.count()).select_from(Refund)) == before


def test_final_sale_refund_denied(ctx):
    result = call(
        ctx,
        "submit_refund_request",
        order_id="ORD-1004",
        reason_code="changed_mind",
        sku="SKU-LMP-01",
    )
    assert not result.ok
    assert result.error == "FINAL_SALE"


def test_over_threshold_creates_pending_approval_not_a_refund(ctx):
    result = call(
        ctx, "submit_refund_request", order_id="ORD-1005", reason_code="damaged", sku="SKU-WCH-01"
    )
    assert result.ok
    assert result.data["status"] == "pending_approval"
    order = ctx.session.get(Order, "ORD-1005")
    assert order.status == "delivered"  # not refunded
    approval = ctx.session.scalar(select(Approval))
    assert approval is not None and approval.status == "pending"


def test_already_refunded_order_denied(ctx):
    result = call(
        ctx, "submit_refund_request", order_id="ORD-1006", reason_code="damaged", sku="SKU-MUG-01"
    )
    assert not result.ok
    assert result.error == "ALREADY_REFUNDED"


def test_repeated_refund_for_different_reason_is_blocked(ctx):
    first = call(
        ctx, "submit_refund_request", order_id="ORD-1001", reason_code="damaged", sku="SKU-HDP-01"
    )
    assert first.ok
    second = call(
        ctx, "submit_refund_request", order_id="ORD-1001", reason_code="defective", sku="SKU-HDP-01"
    )
    # Second reason is a distinct idempotency key, so policy must block it on value.
    assert second.ok and second.data.get("deduplicated") is True or not second.ok
    total = sum(
        r.amount_cents
        for r in ctx.session.scalars(select(Refund).where(Refund.order_id == "ORD-1001"))
    )
    assert total == 12900


# --- returns and replacements ----------------------------------------------


def test_return_within_defective_window(ctx):
    result = call(
        ctx, "create_return_request", order_id="ORD-1008", reason_code="damaged", sku="SKU-JKT-01"
    )
    assert result.ok
    assert result.data["label_code"].startswith("RMA-")
    req = ctx.session.get(ReturnRequest, result.data["return_request_id"])
    label = ctx.session.scalar(select(ReturnLabel).where(ReturnLabel.return_request_id == req.id))
    assert req.status == "created" and label is not None


def test_return_denied_after_standard_window_for_change_of_mind(ctx):
    result = call(
        ctx,
        "create_return_request",
        order_id="ORD-1008",
        reason_code="changed_mind",
        sku="SKU-JKT-01",
    )
    assert not result.ok
    assert result.error == "OUT_OF_WINDOW"
    assert ctx.session.scalar(select(func.count()).select_from(ReturnRequest)) == 0


def test_replacement_requires_a_defect(ctx):
    bad = call(
        ctx,
        "create_replacement_request",
        order_id="ORD-1010",
        reason_code="changed_mind",
        sku="SKU-SPK-01",
    )
    assert not bad.ok
    good = call(
        ctx,
        "create_replacement_request",
        order_id="ORD-1010",
        reason_code="damaged",
        sku="SKU-SPK-01",
    )
    assert good.ok
    assert ctx.session.scalar(select(func.count()).select_from(ReplacementRequest)) == 1


# --- cancellation -----------------------------------------------------------


def test_cancellation_before_shipping(ctx):
    result = call(ctx, "request_cancellation", order_id="ORD-1003")
    assert result.ok
    order = ctx.session.get(Order, "ORD-1003")
    assert order.status == "cancelled"
    refund = ctx.session.get(Refund, result.data["refund_id"])
    assert refund.status == "processed"
    assert refund.amount_cents == order.total_cents


def test_cancellation_after_shipping_refused(ctx):
    result = call(ctx, "request_cancellation", order_id="ORD-1007")
    assert not result.ok
    assert result.error == "ALREADY_SHIPPED"
    assert ctx.session.get(Order, "ORD-1007").status == "shipped"


def test_cancellation_is_idempotent(ctx):
    first = call(ctx, "request_cancellation", order_id="ORD-1003")
    second = call(ctx, "request_cancellation", order_id="ORD-1003")
    assert first.ok
    # Second attempt is denied by policy (already cancelled) rather than double-refunding.
    assert not second.ok or second.data.get("deduplicated")
    total = sum(
        r.amount_cents
        for r in ctx.session.scalars(select(Refund).where(Refund.order_id == "ORD-1003"))
    )
    assert total == ctx.session.get(Order, "ORD-1003").total_cents


# --- read tools -------------------------------------------------------------


def test_warranty_expired(ctx):
    result = call(ctx, "check_warranty", order_id="ORD-1009", sku="SKU-BAG-01")
    assert result.ok
    assert result.data["reason_code"] == "WARRANTY_EXPIRED"


def test_policy_retrieval_returns_versioned_source(ctx):
    result = call(ctx, "retrieve_policy", query="return window days")
    assert result.ok
    assert result.data["count"] > 0
    assert result.data["results"][0]["doc_id"].startswith("pol")


def test_product_catalog_search(ctx):
    result = call(ctx, "search_product_catalog", query="headphones")
    assert result.ok
    assert result.data["count"] == 1
    assert result.data["results"][0]["sku"] == "SKU-HDP-01"


def test_failed_tool_does_not_leave_partial_state(ctx):
    before = ctx.session.scalar(select(func.count()).select_from(ReturnRequest))
    call(
        ctx,
        "create_return_request",
        order_id="ORD-1002",
        reason_code="changed_mind",
        sku="SKU-SHO-01",
    )
    after = ctx.session.scalar(select(func.count()).select_from(ReturnRequest))
    assert before == after


def test_audit_trail_records_denials(ctx):
    from support_ai.db import AuditLog

    call(
        ctx,
        "submit_refund_request",
        order_id="ORD-1002",
        reason_code="changed_mind",
        sku="SKU-SHO-01",
    )
    rows = list(ctx.session.scalars(select(AuditLog).where(AuditLog.decision == "DENY")))
    assert any(r.reason_code == "OUT_OF_WINDOW" for r in rows)


def test_concurrent_identical_refunds_create_exactly_one_row(tmp_path):
    """The unique key is the backstop: a race may lose safely, but never double-pay."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from support_ai.db import Base
    from support_ai.orchestrator import start_conversation
    from support_ai.retrieval import Retriever
    from support_ai.seed import seed

    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    setup = factory()
    seed(setup)
    conv_ids = [start_conversation(setup, 1).id for _ in range(6)]
    setup.close()

    retriever = Retriever.from_directory()
    barrier = threading.Barrier(len(conv_ids))

    def worker(conv_id: int):
        s = factory()
        local = ToolContext(
            session=s,
            customer_id=1,
            conversation_id=conv_id,
            correlation_id=f"race-{conv_id}",
            retriever=retriever,
        )
        barrier.wait()
        try:
            return call(
                local,
                "submit_refund_request",
                order_id="ORD-1001",
                reason_code="damaged",
                sku="SKU-HDP-01",
            )
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=len(conv_ids)) as pool:
        results = list(pool.map(worker, conv_ids))

    check = factory()
    rows = list(
        check.scalars(
            select(Refund).where(Refund.order_id == "ORD-1001", Refund.reason == "damaged")
        )
    )
    check.close()

    assert len(rows) == 1
    assert rows[0].status == "processed"
    assert any(r.ok for r in results)
    # A losing racer may fail closed; it must never report a second refund.
    assert all(r.ok or r.error == "TOOL_FAILURE" for r in results)


def test_replacement_under_threshold_auto_approves(ctx):
    # ORD-1001 has SKU-CAB-01 ($14.90, <= $150 threshold)
    res = call(ctx, "create_replacement_request", order_id="ORD-1001", sku="SKU-CAB-01", reason_code="damaged")
    assert res.ok
    assert res.data["status"] == "created"
    assert res.data["eta_days"] == 3


def test_replacement_over_threshold_creates_sop_approval(ctx):
    # ORD-1005 has SKU-WCH-01 ($199.00, Tier 2 Senior Agent)
    res = call(ctx, "create_replacement_request", order_id="ORD-1005", sku="SKU-WCH-01", reason_code="defective")
    assert res.ok
    assert res.data["status"] == "pending_approval"
    assert res.data["sop_tier"] == 2
    assert "Senior Support Agent" in res.data["sop_required_role"]

    from support_ai.db import SopApproval
    sop_row = ctx.session.scalar(select(SopApproval).where(SopApproval.order_id == "ORD-1005", SopApproval.action_type == "replacement"))
    assert sop_row is not None
    assert sop_row.amount_cents == 19900
    assert sop_row.sop_tier == 2
    assert sop_row.status == "pending"


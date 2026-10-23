import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from support_ai.db import (  # noqa: E402
    Base,
    Order,
    OrderItem,
    Product,
    Refund,
    Warranty,
)
from support_ai.orchestrator import start_conversation  # noqa: E402
from support_ai.retrieval import Retriever  # noqa: E402
from support_ai.seed import seed  # noqa: E402
from support_ai.tools import ToolContext  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = factory()
    seed(s)
    yield s
    s.close()


@pytest.fixture()
def retriever() -> Retriever:
    return Retriever.from_directory()


@pytest.fixture()
def ctx(session, retriever, conversation):
    return ToolContext(
        session=session,
        customer_id=1,
        conversation_id=conversation.id,
        correlation_id="test-trace",
        retriever=retriever,
    )


@pytest.fixture()
def conversation(session):
    return start_conversation(session, 1)


@pytest.fixture()
def make_order(session):
    def _make(
        order_id: str,
        customer_id: int,
        sku: str,
        qty: int = 1,
        delivered_days: int | None = 5,
        status: str = "delivered",
        prior_refund: int = 0,
    ) -> Order:
        product = session.get(Product, sku)
        assert product is not None
        total = product.price_cents * qty
        delivered = (
            datetime.utcnow() - timedelta(days=delivered_days)
            if delivered_days is not None
            else None
        )
        order = Order(
            id=order_id,
            customer_id=customer_id,
            status=status,
            placed_at=datetime.utcnow() - timedelta(days=(delivered_days or 0) + 3),
            delivered_at=delivered,
            total_cents=total,
            payment_status="captured",
        )
        session.add(order)
        session.flush()
        session.add(
            OrderItem(order_id=order_id, sku=sku, qty=qty, unit_price_cents=product.price_cents)
        )
        if delivered:
            session.add(
                Warranty(order_id=order_id, sku=sku, expires_at=delivered + timedelta(days=365))
            )
        if prior_refund:
            session.add(
                Refund(
                    order_id=order_id,
                    amount_cents=prior_refund,
                    status="processed",
                    reason="test",
                    idempotency_key=f"{order_id}:prior",
                )
            )
        session.commit()
        return order

    return _make

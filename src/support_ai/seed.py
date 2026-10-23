"""Deterministic synthetic company: products, customers, orders, shipments, warranties.

`python -m support_ai.seed` rebuilds the demo database from scratch. Evaluation runs
build their own isolated fixtures instead of relying on this data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .config import ROOT
from .db import (
    Base,
    Customer,
    Order,
    OrderItem,
    Payment,
    PolicyDocument,
    Product,
    Refund,
    Shipment,
    TrackingEvent,
    Warranty,
    engine,
)
from .retrieval import Retriever

NOW = datetime.utcnow()


PRODUCTS = [
    # sku, name, category, price, final_sale, returnable, warranty_months, stock, specs
    (
        "SKU-HDP-01",
        "Aurora Wireless Headphones",
        "Audio",
        12900,
        False,
        True,
        12,
        42,
        {"battery_hours": 30, "anc": True, "bluetooth": "5.3"},
    ),
    (
        "SKU-KBD-01",
        "Nimbus Mechanical Keyboard",
        "Peripherals",
        8900,
        False,
        True,
        24,
        30,
        {"layout": "75%", "switches": "brown", "wireless": True},
    ),
    (
        "SKU-MUG-01",
        "Ceramic Travel Mug",
        "Home",
        1900,
        False,
        True,
        6,
        120,
        {"capacity_ml": 350, "dishwasher_safe": True},
    ),
    (
        "SKU-JKT-01",
        "Stormline Rain Jacket",
        "Apparel",
        14900,
        False,
        True,
        12,
        25,
        {"waterproof_mm": 10000, "sizes": "S-XXL"},
    ),
    (
        "SKU-SHO-01",
        "Trailhead Running Shoes",
        "Footwear",
        9900,
        False,
        True,
        6,
        60,
        {"drop_mm": 8, "sizes": "UK 4-13"},
    ),
    (
        "SKU-CAB-01",
        "USB-C Braided Cable 2m",
        "Accessories",
        1490,
        False,
        True,
        12,
        300,
        {"length_m": 2, "wattage": 100},
    ),
    (
        "SKU-CHR-01",
        "ErgoDesk Laptop Stand",
        "Home",
        3900,
        False,
        True,
        24,
        45,
        {"max_inches": 17, "material": "aluminium"},
    ),
    (
        "SKU-LMP-01",
        "Halo Desk Lamp",
        "Home",
        4900,
        True,
        True,
        12,
        18,
        {"lumens": 600, "dimmable": True},
    ),
    (
        "SKU-BAG-01",
        "Voyager 24L Backpack",
        "Bags",
        7900,
        False,
        True,
        24,
        40,
        {"litres": 24, "laptop_inches": 16},
    ),
    (
        "SKU-WCH-01",
        "Pulse Smart Watch",
        "Wearables",
        19900,
        False,
        True,
        12,
        22,
        {"battery_days": 7, "water_resistance": "5ATM"},
    ),
    (
        "SKU-SPK-01",
        "Echo Mini Speaker",
        "Audio",
        5900,
        False,
        True,
        12,
        55,
        {"battery_hours": 12, "waterproof": "IPX7"},
    ),
    (
        "SKU-TEE-01",
        "Everyday Cotton Tee",
        "Apparel",
        2400,
        False,
        True,
        3,
        200,
        {"material": "organic cotton", "sizes": "XS-XXL"},
    ),
]

CUSTOMERS = [
    (1, "Ada Lovelace", "ada@example.test"),
    (2, "Ben Osei", "ben@example.test"),
    (3, "Chen Wei", "chen@example.test"),
    (4, "Dana Ruiz", "dana@example.test"),
    (5, "Eli Novak", "eli@example.test"),
]

# order_id, customer_id, status, days_since_placed, days_since_delivered|None,
# shipping, payment, [(sku, qty)]
ORDERS = [
    (
        "ORD-1001",
        1,
        "delivered",
        8,
        5,
        "delivered",
        "captured",
        [("SKU-HDP-01", 1), ("SKU-CAB-01", 1)],
    ),
    ("ORD-1002", 1, "delivered", 65, 60, "delivered", "captured", [("SKU-SHO-01", 1)]),
    ("ORD-1003", 1, "placed", 1, None, "not_shipped", "captured", [("SKU-WCH-01", 1)]),
    ("ORD-1004", 1, "delivered", 14, 10, "delivered", "captured", [("SKU-LMP-01", 1)]),
    ("ORD-1005", 1, "delivered", 6, 3, "delivered", "captured", [("SKU-WCH-01", 1)]),
    ("ORD-1006", 1, "refunded", 25, 20, "delivered", "refunded", [("SKU-MUG-01", 1)]),
    ("ORD-1007", 1, "shipped", 3, None, "in_transit", "captured", [("SKU-KBD-01", 1)]),
    ("ORD-1008", 1, "delivered", 45, 40, "delivered", "captured", [("SKU-JKT-01", 1)]),
    ("ORD-1009", 1, "delivered", 200, 195, "delivered", "captured", [("SKU-BAG-01", 1)]),
    ("ORD-1010", 1, "delivered", 4, 2, "delivered", "captured", [("SKU-SPK-01", 1)]),
    ("ORD-2001", 2, "delivered", 7, 4, "delivered", "captured", [("SKU-HDP-01", 1)]),
    ("ORD-2002", 2, "delivered", 5, 2, "delivered", "captured", [("SKU-CHR-01", 1)]),
    ("ORD-3001", 3, "delivered", 9, 6, "delivered", "captured", [("SKU-KBD-01", 1)]),
    ("ORD-4001", 4, "placed", 0, None, "not_shipped", "captured", [("SKU-TEE-01", 2)]),
    ("ORD-5001", 5, "delivered", 18, 15, "delivered", "captured", [("SKU-BAG-01", 1)]),
]


def seed(session: Session) -> dict:
    prices = {p[0]: p[3] for p in PRODUCTS}
    for sku, name, category, price, final_sale, returnable, warranty, stock, specs in PRODUCTS:
        session.add(
            Product(
                sku=sku,
                name=name,
                category=category,
                price_cents=price,
                description=f"{name} — synthetic catalogue item used for demo and evaluation.",
                specs=json.dumps(specs),
                final_sale=final_sale,
                returnable=returnable,
                warranty_months=warranty,
                in_stock=stock,
            )
        )

    for cid, name, email in CUSTOMERS:
        session.add(Customer(id=cid, name=name, email=email))
    session.flush()

    for oid, cid, status, placed_days, delivered_days, ship_status, pay_status, items in ORDERS:
        placed = NOW - timedelta(days=placed_days)
        delivered = NOW - timedelta(days=delivered_days) if delivered_days is not None else None
        total = sum(prices[sku] * qty for sku, qty in items)
        order = Order(
            id=oid,
            customer_id=cid,
            status=status,
            placed_at=placed,
            delivered_at=delivered,
            total_cents=total,
            payment_status=pay_status,
            shipping_address=f"{cid} Example Street, Testville",
        )
        session.add(order)
        session.flush()
        for sku, qty in items:
            session.add(OrderItem(order_id=oid, sku=sku, qty=qty, unit_price_cents=prices[sku]))
            months = next(p[6] for p in PRODUCTS if p[0] == sku)
            if delivered is not None:
                expires = delivered + timedelta(days=30 * months)
                if oid == "ORD-1009":
                    expires = NOW - timedelta(days=10)  # deliberately expired warranty
                session.add(Warranty(order_id=oid, sku=sku, expires_at=expires))

        session.add(
            Payment(
                order_id=oid,
                amount_cents=total,
                status="refunded" if pay_status == "refunded" else "captured",
                provider_ref=f"mock_{oid.lower()}",
                created_at=placed,
            )
        )

        if ship_status != "not_shipped":
            ship = Shipment(
                order_id=oid,
                carrier="MockPost",
                tracking=f"MP{oid.split('-')[1]}XX",
                status="delivered" if ship_status == "delivered" else "in_transit",
                eta=delivered or (NOW + timedelta(days=2)),
            )
            session.add(ship)
            session.flush()
            session.add(
                TrackingEvent(
                    shipment_id=ship.id,
                    ts=placed + timedelta(days=1),
                    status="picked_up",
                    location="Testville Depot",
                )
            )
            if ship_status == "delivered":
                session.add(
                    TrackingEvent(
                        shipment_id=ship.id,
                        ts=delivered or NOW,
                        status="delivered",
                        location="Customer address",
                    )
                )

    # Pre-existing processed refund on ORD-1006 (duplicate-refund scenario).
    session.add(
        Refund(
            order_id="ORD-1006",
            amount_cents=prices["SKU-MUG-01"],
            status="processed",
            reason="damaged",
            idempotency_key="seed:ORD-1006:refund",
            created_at=NOW - timedelta(days=18),
        )
    )

    # Policy documents mirror the markdown files that retrieval reads.
    retriever = Retriever.from_directory(ROOT / "data" / "policy")
    seen: set[str] = set()
    for chunk in retriever.chunks:
        if chunk.doc_id in seen:
            continue
        seen.add(chunk.doc_id)
        session.add(
            PolicyDocument(
                doc_id=chunk.doc_id,
                title=chunk.title,
                version=chunk.version or "2026.1",
                effective_from=datetime(2026, 1, 1),
                body=chunk.text,
            )
        )
    session.commit()
    return {"products": len(PRODUCTS), "customers": len(CUSTOMERS), "orders": len(ORDERS)}


def reset_and_seed() -> dict:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        info = seed(session)
    return info


if __name__ == "__main__":
    print(reset_and_seed())

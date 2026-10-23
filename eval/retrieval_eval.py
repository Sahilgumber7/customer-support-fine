"""Retrieval evaluation: recall@k and MRR over a small labelled query set.

The set is deliberately policy-shaped (real customer phrasings), not keyword echoes.
"""

from __future__ import annotations

import json
from pathlib import Path

from support_ai.retrieval import Retriever

ROOT = Path(__file__).resolve().parents[1]

QUERIES: list[tuple[str, tuple[str, ...]]] = [
    ("how many days do I have to send something back", ("pol_returns",)),
    ("can I return a final sale item if I changed my mind", ("pol_returns",)),
    ("item arrived damaged what are my options", ("pol_returns",)),
    ("what is the refund approval limit", ("pol_refunds",)),
    ("how long does a refund take to reach my card", ("pol_refunds", "faq_general")),
    ("can I cancel after the parcel shipped", ("pol_refunds", "help_orders")),
    ("my parcel is late past the estimated delivery date", ("pol_shipping",)),
    ("when is a parcel considered lost", ("pol_shipping",)),
    ("can I change the delivery address", ("pol_shipping",)),
    ("is the fault covered under warranty", ("pol_warranty",)),
    ("warranty excludes accidental damage", ("pol_warranty",)),
    ("how do I track my order", ("help_orders",)),
    ("I was charged twice for one order", ("faq_general",)),
    ("which size should I order", ("faq_general",)),
]


def run(k: int = 4) -> dict:
    retriever = Retriever.from_directory()
    hits = 0
    reciprocal = 0.0
    rows = []
    for query, expected in QUERIES:
        results = retriever.search(query, k=k)
        ids = [c.doc_id for c in results]
        rank = next((i + 1 for i, doc in enumerate(ids) if doc in expected), 0)
        hits += int(rank > 0)
        reciprocal += (1.0 / rank) if rank else 0.0
        rows.append(
            {"query": query, "expected": list(expected), "rank": rank, "returned": ids}
        )

    summary = {
        "n": len(QUERIES),
        "k": k,
        "recall_at_k": round(hits / len(QUERIES), 4),
        "mrr": round(reciprocal / len(QUERIES), 4),
        "rows": rows,
    }
    out = ROOT / "EVALUATION_RESULTS" / "retrieval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run()
    print(json.dumps({k: result[k] for k in ("n", "k", "recall_at_k", "mrr")}, indent=2))
    for row in result["rows"]:
        if row["rank"] == 0:
            print("MISS:", row["query"], "->", row["returned"])


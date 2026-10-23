"""Model backends.

`RulesBackend` is a deterministic planner used for offline development, tests, and as the
no-LLM baseline in the evaluation. `LlamaCppBackend` serves the fine-tuned Qwen2.5-3B
GGUF checkpoint. Both implement the same narrow interface, so swapping them cannot change
authorisation: only tools decide, and tools ignore everything the model says about identity.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from .config import settings
from .schemas import Entities, FinalResponse, Plan, ToolCall, Understanding

ORDER_RE = re.compile(r"\bORD-\d{4}\b", re.IGNORECASE)
SKU_RE = re.compile(r"\bSKU-[A-Z]{3}-\d{2}\b", re.IGNORECASE)

REASON_PATTERNS = [
    ("damaged", r"\b(damaged|smashed|cracked|broken|arrived broken)\b"),
    ("defective", r"\b(defective|faulty|not working|doesn'?t work|stopped working)\b"),
    ("wrong_item", r"\b(wrong item|wrong colour|wrong color|sent the wrong)\b"),
    ("missing_item", r"\b(missing|not in the box|never arrived inside)\b"),
    ("not_as_described", r"\b(not as described|nothing like the photo|misleading)\b"),
    ("late_delivery", r"\b(late|delayed|still not arrived|never arrived)\b"),
    ("changed_mind", r"\b(changed my mind|don'?t want it|no longer need)\b"),
]


class Backend(Protocol):
    model_id: str

    def understand(self, message: str, history: list[dict[str, str]]) -> Understanding: ...

    def plan(self, u: Understanding, facts: dict[str, dict], message: str = "") -> Plan: ...

    def respond(
        self,
        u: Understanding,
        facts: dict[str, dict],
        action: dict | None,
    ) -> FinalResponse: ...


def _extract_reason(text: str) -> str | None:
    low = text.lower()
    for code, pattern in REASON_PATTERNS:
        if re.search(pattern, low):
            return code
    return None


def _money(cents: int | None) -> str:
    if cents is None:
        return "unknown"
    return f"${cents / 100:,.2f}"


# --- deterministic baseline -------------------------------------------------


class RulesBackend:
    """No-LLM baseline. Deterministic, inspectable, and intentionally conservative."""

    model_id = "rules-baseline"

    def understand(self, message: str, history: list[dict[str, str]]) -> Understanding:
        low = message.lower()
        order_match = ORDER_RE.search(message)
        sku_match = SKU_RE.search(message.upper())
        entities = Entities(
            order_id=order_match.group(0).upper() if order_match else None,
            sku=sku_match.group(0).upper() if sku_match else None,
            reason_code=_extract_reason(message) or None,
        )

        intent = "other"
        if re.search(r"\b(cancel|cancellation)\b", low):
            intent = "cancellation_request"
        elif re.search(r"\b(replacement|replace|exchange)\b", low):
            intent = "replacement_request"
        elif re.search(r"\b(return|send (it|them) back)\b", low):
            intent = "return_request"
        elif re.search(r"\bwarranty|guarantee\b", low):
            intent = "warranty_claim"
        elif re.search(r"\b(charged twice|double charge|duplicate charge)\b", low):
            intent = "payment_issue"
        elif re.search(r"\b(refund|money back|reimburse)\b", low) or re.search(
            r"\b(broken|damaged|faulty|defective|not working|doesn'?t work|stopped working|"
            r"falling apart|ripped|empty box|arrived empty|missing item)\b",
            low,
        ):
            intent = "refund_request"
        elif re.search(
            r"\b(where('s| is)|tracking|track|delivered|shipping status|order status|eta)\b", low
        ):
            intent = "order_status"
        elif re.search(
            r"\b(size|sizing|compatible|spec|dimension|how do i use|waterproof|battery)\b", low
        ):
            intent = "product_info"
        elif re.search(r"\b(human|agent|person|representative|manager|supervisor)\b", low):
            intent = "human_handoff"
        elif re.search(
            r"\b(angry|unacceptable|terrible|worst|complaint|disappointed|furious)\b", low
        ):
            intent = "complaint"

        needs_order = intent in {
            "order_status",
            "refund_request",
            "return_request",
            "replacement_request",
            "cancellation_request",
            "warranty_claim",
            "payment_issue",
        }
        if needs_order and not entities.order_id:
            return Understanding(
                intent=intent,  # type: ignore[arg-type]
                entities=entities,
                needs_clarification=True,
                clarification_question=(
                    "Could you share the order number (it usually looks like ORD-1234) so I can "
                    "look into this for you?"
                ),
                confidence=0.9,
            )

        return Understanding(
            intent=intent,  # type: ignore[arg-type]
            entities=entities,
            confidence=0.65 if intent == "other" else 0.92,
        )

    def plan(self, u: Understanding, facts: dict[str, dict], message: str = "") -> Plan:
        e = u.entities
        calls: list[ToolCall] = []

        if u.intent == "order_status" and e.order_id:
            if "get_order" not in facts:
                calls = [
                    ToolCall(name="get_order", arguments={"order_id": e.order_id}),
                    ToolCall(name="get_shipment_status", arguments={"order_id": e.order_id}),
                ]
            return Plan(tool_calls=calls)

        if u.intent == "product_info":
            if e.sku:
                return Plan(
                    tool_calls=[ToolCall(name="get_product_details", arguments={"sku": e.sku})]
                )
            if not facts:
                query = e.product_name or "product"
                return Plan(
                    tool_calls=[
                        ToolCall(name="search_product_catalog", arguments={"query": query}),
                        ToolCall(name="search_help_center", arguments={"query": query}),
                    ]
                )
            return Plan()

        if u.intent in {"complaint", "human_handoff"}:
            return Plan(
                tool_calls=[
                    ToolCall(
                        name="escalate_to_human",
                        arguments={
                            "reason": "customer_requested_human"
                            if u.intent == "human_handoff"
                            else "customer_complaint",
                            "summary": "Customer asked for a human or raised a complaint.",
                        },
                    )
                ],
                proposed_resolution="escalate",
            )

        if u.intent == "payment_issue" and e.order_id:
            if "get_refund_status" not in facts:
                return Plan(
                    tool_calls=[
                        ToolCall(name="get_order", arguments={"order_id": e.order_id}),
                        ToolCall(name="get_refund_status", arguments={"order_id": e.order_id}),
                    ]
                )
            return Plan(
                tool_calls=[
                    ToolCall(
                        name="escalate_to_human",
                        arguments={
                            "reason": "payment_investigation",
                            "summary": "Possible duplicate charge; needs payment team review.",
                        },
                    )
                ],
                proposed_resolution="escalate",
            )

        if u.intent == "warranty_claim" and e.order_id:
            if "check_warranty" not in facts:
                order = facts.get("get_order")
                sku = e.sku or (_single_sku(order) if order else None)
                if sku:
                    return Plan(
                        tool_calls=[
                            ToolCall(
                                name="check_warranty",
                                arguments={"order_id": e.order_id, "sku": sku},
                            )
                        ]
                    )
                if order is None:
                    return Plan(
                        tool_calls=[ToolCall(name="get_order", arguments={"order_id": e.order_id})]
                    )
                return Plan(note="customer must name the item")
            verdict = facts["check_warranty"]
            if verdict.get("decision") == "ALLOW":
                return Plan(
                    tool_calls=[
                        ToolCall(
                            name="create_support_ticket",
                            arguments={
                                "subject": "Warranty claim",
                                "body": "Customer reported a fault.",
                            },
                        )
                    ],
                    proposed_resolution="warranty_ticket",
                )
            return Plan()

        if u.intent in {
            "refund_request",
            "return_request",
            "replacement_request",
            "cancellation_request",
        }:
            if not e.order_id:
                return Plan()
            if "get_order" not in facts:
                return Plan(
                    tool_calls=[ToolCall(name="get_order", arguments={"order_id": e.order_id})]
                )

            order = facts["get_order"]
            if order.get("error"):
                return Plan()
            sku = e.sku or _single_sku(order) or _match_sku(order, message)
            reason = e.reason_code or "other"

            if u.intent == "cancellation_request":
                if "request_cancellation" in facts:
                    return Plan()
                return Plan(
                    tool_calls=[
                        ToolCall(
                            name="request_cancellation",
                            arguments={"order_id": e.order_id, "reason": "customer_request"},
                        )
                    ],
                    proposed_resolution="cancel_order",
                )

            if sku is None:
                return Plan()  # multi-item order and no item named: ask in the response

            if "check_return_eligibility" not in facts:
                return Plan(
                    tool_calls=[
                        ToolCall(
                            name="check_return_eligibility",
                            arguments={
                                "order_id": e.order_id,
                                "sku": sku,
                                "reason_code": reason,
                            },
                        )
                    ]
                )

            eligibility = facts["check_return_eligibility"]
            if eligibility.get("decision") != "ALLOW":
                return Plan()

            if u.intent == "refund_request" and "submit_refund_request" not in facts:
                return Plan(
                    tool_calls=[
                        ToolCall(
                            name="submit_refund_request",
                            arguments={
                                "order_id": e.order_id,
                                "sku": sku,
                                "reason_code": reason,
                            },
                        )
                    ],
                    proposed_resolution="refund",
                )
            if u.intent == "return_request" and "create_return_request" not in facts:
                return Plan(
                    tool_calls=[
                        ToolCall(
                            name="create_return_request",
                            arguments={
                                "order_id": e.order_id,
                                "sku": sku,
                                "reason_code": reason,
                            },
                        )
                    ],
                    proposed_resolution="return",
                )
            if u.intent == "replacement_request" and "create_replacement_request" not in facts:
                return Plan(
                    tool_calls=[
                        ToolCall(
                            name="create_replacement_request",
                            arguments={
                                "order_id": e.order_id,
                                "sku": sku,
                                "reason_code": reason,
                            },
                        )
                    ],
                    proposed_resolution="replacement",
                )
            return Plan()

        # fallback: knowledge lookup
        if "search_help_center" not in facts:
            return Plan(
                tool_calls=[ToolCall(name="search_help_center", arguments={"query": "order help"})]
            )
        return Plan()

    def respond(
        self, u: Understanding, facts: dict[str, dict], action: dict | None
    ) -> FinalResponse:
        e = u.entities
        order = facts.get("get_order") or {}
        eligibility = facts.get("check_return_eligibility") or {}

        if u.needs_clarification:
            return FinalResponse(
                customer_message=u.clarification_question or "Could you share more detail?",
            )

        if order_error := (facts.get("get_order") or {}).get("error"):
            return FinalResponse(customer_message=_deny_copy(order_error, {}, {}))

        # 1) action outcome, reported only as far as the backend confirmed it
        if action:
            tool, ok = action.get("tool"), action.get("ok")
            data = action.get("data") or {}
            if ok and tool == "submit_refund_request":
                if data.get("status") == "pending_approval":
                    return FinalResponse(
                        customer_message=(
                            f"I've submitted a refund of {_money(data.get('amount_cents'))} on "
                            f"{data.get('order_id')} for review, since it's above our automatic "
                            "approval limit. Your reference is "
                            f"REF-{data.get('refund_id'):04d}. You'll hear back within one "
                            "business day, and refunds then take 5–7 business days to appear."
                        ),
                        cites=["POL-REF"],
                    )
                return FinalResponse(
                    customer_message=(
                        f"Done — a refund of {_money(data.get('amount_cents'))} has been issued for "
                        f"{data.get('order_id')}. It will appear on your original payment method in "
                        "5–7 business days. Your refund reference is "
                        f"REF-{data.get('refund_id'):04d}."
                    ),
                    cites=["POL-REF"],
                )
            if ok and tool == "create_return_request":
                return FinalResponse(
                    customer_message=(
                        f"Your return is created for {data.get('sku')} on {data.get('order_id')}. "
                        f"Your prepaid label is {data.get('label_code')}, valid until "
                        f"{str(data.get('label_expires_at'))[:10]}. Drop the parcel at any MockPost "
                        "counter and the refund is issued once it's scanned."
                    ),
                    cites=["POL-RET"],
                )
            if ok and tool == "create_replacement_request":
                return FinalResponse(
                    customer_message=(
                        f"A replacement for {data.get('sku')} is on its way — reference "
                        f"REP-{data.get('replacement_request_id'):04d}, usually arriving in about "
                        f"{data.get('eta_days')} days. Keep the original item until it arrives."
                    ),
                    cites=["POL-RET"],
                )
            if ok and tool == "request_cancellation":
                return FinalResponse(
                    customer_message=(
                        f"{data.get('order_id')} is cancelled, and a refund of "
                        f"{_money(data.get('refund_amount_cents'))} has been issued to your original "
                        "payment method. It typically appears within 5–7 business days."
                    ),
                    cites=["POL-REF"],
                )
            if ok and tool == "escalate_to_human":
                return FinalResponse(
                    customer_message=(
                        "I've passed this to a specialist. Your case reference is "
                        f"{data.get('case_reference')}, and someone will pick it up shortly."
                    ),
                    escalate=True,
                    escalate_reason="customer_or_policy_escalation",
                )
            if ok and tool == "create_support_ticket":
                return FinalResponse(
                    customer_message=(
                        f"I've opened a warranty claim for you — ticket #{data.get('ticket_id')}. "
                        "Our team will review the fault and confirm the next step by email."
                    ),
                    cites=["POL-WAR"],
                )
            if not ok:
                code = action.get("error", "TOOL_FAILURE")
                detail = (action.get("data") or {}).get("message", "")
                if code == "ALREADY_REFUNDED":
                    friendly = _deny_copy(code, order, eligibility)
                else:
                    friendly = detail or _deny_copy(code, order, eligibility)
                return FinalResponse(customer_message=friendly, cites=["POL-RET"])

        # 2) no action: answer from verified facts
        if u.intent == "order_status" and order:
            ship = facts.get("get_shipment_status") or {}
            ship_status = ship.get("status") or order.get("status")
            if ship_status == "delivered" or order.get("status") == "delivered":
                body = f"{order.get('order_id')} was delivered. Items: {_items_copy(order)}."
            elif ship_status in {"in_transit", "shipped"}:
                if ship.get("carrier"):
                    body = (
                        f"{order.get('order_id')} is in transit with {ship.get('carrier')} "
                        f"(tracking {ship.get('tracking')}), estimated "
                        f"{str(ship.get('eta'))[:10]}."
                    )
                else:
                    body = f"{order.get('order_id')} has shipped and is on its way."
            else:
                body = f"{order.get('order_id')} is {order.get('status')} and hasn't shipped yet."
            return FinalResponse(customer_message=body, cites=["POL-SHIP"])

        if u.intent in {"refund_request", "return_request", "replacement_request"}:
            if eligibility and eligibility.get("decision") != "ALLOW":
                return FinalResponse(
                    customer_message=_deny_copy(
                        eligibility.get("reason_code", ""), order, eligibility
                    ),
                    cites=["POL-RET"],
                )
            if order and _single_sku(order) is None and not e.sku:
                return FinalResponse(
                    customer_message=(
                        f"{order.get('order_id')} has more than one item — which product should "
                        "this be for? You can name it or give me the SKU."
                    )
                )
            return FinalResponse(
                customer_message=_deny_copy("OTHER", order, eligibility),
                cites=["POL-RET"],
            )

        if u.intent == "product_info":
            product = facts.get("get_product_details")
            if product:
                specs = ", ".join(f"{k}: {v}" for k, v in (product.get("specs") or {}).items())
                return FinalResponse(
                    customer_message=(
                        f"{product.get('name')} ({product.get('sku')}) is "
                        f"{_money(product.get('price_cents'))}. Specs — {specs or 'see the product page'}. "
                        f"Warranty: {product.get('warranty_months')} months."
                    ),
                    cites=["FAQ-GEN"],
                )
            catalog = facts.get("search_product_catalog") or {}
            if catalog.get("results"):
                names = "; ".join(
                    f"{r['name']} ({r['sku']}, {_money(r['price_cents'])})"
                    for r in catalog["results"][:3]
                )
                return FinalResponse(customer_message=f"I found: {names}.", cites=["FAQ-GEN"])

        if u.intent == "warranty_claim":
            warranty = facts.get("check_warranty") or {}
            if warranty:
                return FinalResponse(
                    customer_message=(
                        f"Your warranty for {warranty.get('sku')} is "
                        f"{'active' if warranty.get('decision') == 'ALLOW' else 'not active'} — "
                        f"{warranty.get('explanation')}"
                    ),
                    cites=["POL-WAR"],
                )

        if u.intent == "payment_issue":
            refund = facts.get("get_refund_status") or {}
            if refund:
                return FinalResponse(
                    customer_message=(
                        f"I can see {_money(refund.get('refunded_cents'))} has been refunded on "
                        f"{refund.get('order_id')}, with {_money(refund.get('refundable_cents'))} "
                        "still refundable. A payment investigation has been opened for the duplicate "
                        "charge; duplicate authorisations normally reverse within 3 business days."
                    ),
                    cites=["FAQ-GEN"],
                )

        if u.intent in {"complaint", "human_handoff"}:
            return FinalResponse(
                customer_message="I'm passing you to a human colleague now, with your case history.",
                escalate=True,
                escalate_reason="customer_requested_human",
            )

        help_chunks = (facts.get("search_help_center") or {}).get("results") or []
        if help_chunks:
            return FinalResponse(
                customer_message=help_chunks[0]["text"][:400],
                cites=[help_chunks[0]["doc_id"]],
            )

        return FinalResponse(
            customer_message=(
                "I want to make sure I get this right — could you tell me the order number and "
                "what you'd like me to do?"
            )
        )


def _single_sku(order: dict) -> str | None:
    items = order.get("items") or []
    skus = {i.get("sku") for i in items}
    return skus.pop() if len(skus) == 1 else None


def _match_sku(order: dict, message: str) -> str | None:
    """Match a product mentioned in the message against the order's items."""
    words = {w for w in re.findall(r"[a-z]{4,}", message.lower())}
    for item in order.get("items") or []:
        name_words = set(re.findall(r"[a-z]{4,}", (item.get("name") or "").lower()))
        if words & name_words:
            return item.get("sku")
    return None


def _items_copy(order: dict) -> str:
    return ", ".join(f"{i.get('qty')}× {i.get('name')}" for i in order.get("items") or [])


def _deny_copy(code: str, order: dict, eligibility: dict) -> str:
    reason = eligibility.get("reason_code") or code
    if reason in {"ALLOW", "OK"}:
        reason = code
    mapping = {
        "OUT_OF_WINDOW": (
            "That order is outside the return window. Standard returns close 30 days after "
            "delivery, though damaged or defective items can be reported for 90 days."
        ),
        "FINAL_SALE": (
            "That item was final sale, so it can't be returned for a change of mind. If it arrived "
            "damaged or faulty, tell me and I can handle it under the defective policy."
        ),
        "NOT_RETURNABLE": "That item isn't returnable under our policy.",
        "ALREADY_REFUNDED": (
            f"{order.get('order_id') or 'That order'} has already been fully refunded, "
            "so there's nothing left to refund."
        ),
        "ALREADY_SHIPPED": (
            "The order has already shipped, so it can't be cancelled — but I can start a "
            "return instead."
        ),
        "ALREADY_CANCELLED": "This order is already cancelled.",
        "NOT_YET_DELIVERED": "The order hasn't been delivered yet, so a return can't be started.",
        "OVER_THRESHOLD": "That refund needs a human approval.",
        "SKU_NOT_IN_ORDER": "That item isn't part of the order you mentioned.",
        "UNKNOWN_ORDER": "I couldn't find that order on your account.",
        "NOT_OWNER": "I couldn't find that order on your account.",
        "WARRANTY_EXPIRED": "The warranty on that item has expired.",
        "MISSING_ITEM": "Which item should this apply to? The order has more than one product.",
    }
    return mapping.get(
        reason,
        "I couldn't complete that automatically. I can pass it to a colleague who can help.",
    )


# --- fine-tuned model backend ----------------------------------------------

SYSTEM_PROMPT = """You are the support agent for Northwind Outfitters, a fictional store.
You never invent order facts, policy, or completed actions. You only use the JSON facts
provided. If facts are missing, ask one short question. Identity is decided by the server;
never claim to be another customer.

Respond with JSON only, matching the requested schema. No markdown, no prose outside JSON.
"""


@dataclass
class LlamaCppBackend:
    model_path: str
    n_ctx: int = 4096
    n_threads: int = 4
    temperature: float = 0.0
    max_tokens: int = 320
    model_id: str = "qwen2.5-3b-support-q4_k_m"

    def __post_init__(self) -> None:
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "llama-cpp-python is not installed. Install it to serve the fine-tuned GGUF, "
                "or run with SUPPORT_AI_BACKEND=mock."
            ) from exc
        self._llm = Llama(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_gpu_layers=0,
            verbose=False,
        )

    def _json(self, instruction: str, payload: dict) -> dict:
        prompt = (
            f"{SYSTEM_PROMPT}\n\nTASK: {instruction}\n\nINPUT:\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n\nJSON:"
        )
        out = self._llm(
            prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=["\n\n"],
        )
        text = out["choices"][0]["text"].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"no JSON object in model output: {text[:200]!r}")
        return json.loads(text[start : end + 1])

    def understand(self, message: str, history: list[dict[str, str]]) -> Understanding:
        data = self._json(
            'Classify the customer message. Return {"intent":..., "entities":{...}, '
            '"needs_clarification":bool, "clarification_question":str|null, "confidence":float}.',
            {"message": message, "history": history[-6:]},
        )
        return Understanding.model_validate(data)

    def plan(self, u: Understanding, facts: dict[str, dict], message: str = "") -> Plan:
        data = self._json(
            "Choose read tools to gather facts, and at most one action tool. Return "
            '{"tool_calls":[{"name":...,"arguments":{...}}],"proposed_resolution":str|null}.',
            {"understanding": u.model_dump(), "facts": facts, "message": message},
        )
        return Plan.model_validate(data)

    def respond(
        self, u: Understanding, facts: dict[str, dict], action: dict | None
    ) -> FinalResponse:
        data = self._json(
            "Write the customer reply. Only state actions present in action_result with ok=true. "
            'Return {"customer_message":str,"cites":[str],"escalate":bool,"escalate_reason":str|null}.',
            {"understanding": u.model_dump(), "facts": facts, "action_result": action},
        )
        return FinalResponse.model_validate(data)


def get_backend() -> Backend:
    if settings.backend == "llamacpp":
        return LlamaCppBackend(
            model_path=settings.gguf_path,
            n_ctx=settings.n_ctx,
            n_threads=settings.n_threads,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
    return RulesBackend()

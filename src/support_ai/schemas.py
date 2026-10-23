"""Validated contracts between the model, the orchestrator, and the tools.

Stage-scoped schemas: the model never emits one mega-object per turn. Each stage has a
narrow shape that the application validates before anything can execute.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Intent = Literal[
    "order_status",
    "product_info",
    "refund_request",
    "return_request",
    "replacement_request",
    "cancellation_request",
    "warranty_claim",
    "payment_issue",
    "complaint",
    "human_handoff",
    "other",
]

ReasonCode = Literal[
    "damaged",
    "defective",
    "wrong_item",
    "missing_item",
    "not_as_described",
    "changed_mind",
    "late_delivery",
    "other",
]

OrderId = Annotated[str, Field(pattern=r"^ORD-\d{4}$")]

ACTION_TOOLS = {
    "create_return_request",
    "create_replacement_request",
    "request_cancellation",
    "submit_refund_request",
    "create_support_ticket",
    "escalate_to_human",
}

READ_TOOLS = {
    "get_order",
    "get_shipment_status",
    "get_product_details",
    "search_product_catalog",
    "search_help_center",
    "retrieve_policy",
    "check_warranty",
    "get_refund_status",
    "check_return_eligibility",
}


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    # Unknown tool names are rejected by the registry at execution time, where the
    # failure can be returned as a structured result instead of a parse crash.


class Entities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str | None = None
    sku: str | None = None
    product_name: str | None = None
    reason_code: ReasonCode | None = None
    quantity: int | None = Field(default=None, ge=1, le=50)


class Understanding(BaseModel):
    """Stage 1: what the customer wants, and can we act on it."""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    entities: Entities = Field(default_factory=Entities)
    needs_clarification: bool = False
    clarification_question: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("clarification_question")
    @classmethod
    def question_required_when_clarifying(cls, v: str | None, info):
        if info.data.get("needs_clarification") and not v:
            raise ValueError("clarification_question is required when needs_clarification is true")
        return v


class Plan(BaseModel):
    """Stage 2: which tools, and what resolution is being proposed."""

    model_config = ConfigDict(extra="forbid")
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=6)
    proposed_resolution: str | None = None
    note: str | None = None


class FinalResponse(BaseModel):
    """Stage 3: customer-visible text, grounded in verified state only."""

    model_config = ConfigDict(extra="forbid")
    customer_message: str = Field(min_length=1, max_length=2000)
    cites: list[str] = Field(default_factory=list, max_length=5)
    escalate: bool = False
    escalate_reason: str | None = None


class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    trace_id: str = ""


class TraceStep(BaseModel):
    stage: str
    detail: str
    payload: dict[str, object] = Field(default_factory=dict)


class TurnResult(BaseModel):
    conversation_id: int
    message: str
    intent: Intent
    action_taken: str | None = None
    action_reference: str | None = None
    escalated: bool = False
    reason_code: str | None = None
    tool_calls: list[ToolResult] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    latency_ms: int = 0
    model_id: str = "rules-baseline"

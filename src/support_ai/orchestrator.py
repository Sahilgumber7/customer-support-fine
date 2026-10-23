"""Conversation orchestrator: a bounded state machine, not a free-running agent loop.

INTAKE → UNDERSTAND → GATHER → ACT → VERIFY → RESPOND → CLOSE
Every transition is traced. At most `max_tool_calls` tools run, at most one mutates state.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import policy
from .config import settings
from .db import (
    Approval,
    AuditLog,
    Conversation,
    Escalation,
    Message,
    Order,
    Refund,
    ReplacementRequest,
    ReturnLabel,
    ReturnRequest,
    Ticket,
)
from .llm import Backend
from .retrieval import Retriever
from .schemas import (
    ACTION_TOOLS,
    READ_TOOLS,
    FinalResponse,
    ToolCall,
    ToolResult,
    TraceStep,
    TurnResult,
    Understanding,
)
from .tools import ToolContext, execute_tool

ACTION_FOR_INTENT = {
    "refund_request": "submit_refund_request",
    "return_request": "create_return_request",
    "replacement_request": "create_replacement_request",
    "cancellation_request": "request_cancellation",
}


class BackendTimeout(RuntimeError):
    """The backend did not answer within the configured budget."""


def _bounded(fn, *args):
    """Run one backend call under a wall-clock budget.

    The abandoned worker may keep running until it returns; this bounds what the
    customer waits for, not what the process consumes. Documented in DECISIONS D19.
    """
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backend")
    try:
        future = pool.submit(fn, *args)
        return future.result(timeout=settings.backend_timeout_s)
    except FutureTimeout as exc:
        raise BackendTimeout(
            f"backend call exceeded {settings.backend_timeout_s:g}s"
        ) from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def start_conversation(
    session: Session, customer_id: int, subject: str = "Support chat"
) -> Conversation:
    ticket = Ticket(customer_id=customer_id, subject=subject, status="open", channel="chat")
    session.add(ticket)
    session.flush()
    conv = Conversation(ticket_id=ticket.id, customer_id=customer_id, status="open")
    session.add(conv)
    session.commit()
    return conv


class Orchestrator:
    def __init__(
        self,
        session: Session,
        backend: Backend,
        retriever: Retriever,
        customer_id: int,
        conversation_id: int,
        now: datetime | None = None,
    ) -> None:
        self.s = session
        self.backend = backend
        self.retriever = retriever
        self.customer_id = customer_id
        self.conversation_id = conversation_id
        self.now = now
        self.correlation_id = uuid.uuid4().hex[:12]
        self.ctx = ToolContext(
            session=session,
            customer_id=customer_id,
            conversation_id=conversation_id,
            correlation_id=self.correlation_id,
            retriever=retriever,
            now=now,
        )

    # -- public ------------------------------------------------------------

    def handle(self, message: str) -> TurnResult:
        started = time.perf_counter()
        trace: list[TraceStep] = []
        history = self._history()

        self.s.add(Message(conversation_id=self.conversation_id, role="user", content=message))
        self.s.commit()

        try:
            u = _bounded(self.backend.understand, message, history)
        except BackendTimeout:
            return self._timeout_turn(started, trace, "understand")
        trace.append(TraceStep(stage="understand", detail=u.intent, payload=u.model_dump()))

        if u.needs_clarification:
            reply = FinalResponse(
                customer_message=u.clarification_question or "Could you share a bit more detail?"
            )
            return self._finish(reply, u, None, [], trace, started, "REQUIRE_INFORMATION")

        if u.confidence < 0.55:
            verdict = policy.evaluate_escalation(reason="low_confidence", confidence=u.confidence)
            reply = FinalResponse(
                customer_message=(
                    "I want to get this right, so I'm passing you to a colleague who can help."
                ),
                escalate=True,
                escalate_reason=verdict.reason.value,
            )
            return self._finish(reply, u, None, [], trace, started, verdict.reason.value)

        facts: dict[str, dict] = {}
        results: list[ToolResult] = []
        budget = settings.max_tool_calls
        failures = 0

        # ---- bounded gather → act loop (max 3 model planning rounds) ----
        action_payload: dict | None = None
        action_reason: str | None = None
        executed_action = False

        for round_no in range(3):
            if executed_action or budget <= 0 or failures >= 2:
                break
            try:
                plan = _bounded(self.backend.plan, u, facts, message)
            except BackendTimeout:
                return self._timeout_turn(started, trace, "plan")
            trace.append(
                TraceStep(
                    stage="plan",
                    detail=f"round-{round_no + 1}",
                    payload={"calls": [c.name for c in plan.tool_calls]},
                )
            )
            reads = [c for c in plan.tool_calls if c.name in READ_TOOLS and c.name not in facts][
                :budget
            ]
            for call in reads:
                result = execute_tool(self.ctx, call)
                results.append(result)
                budget -= 1
                if result.ok:
                    facts[call.name] = result.data
                else:
                    failures += 1
                    facts[call.name] = {"error": result.error, **(result.data or {})}
                trace.append(
                    TraceStep(
                        stage="tool",
                        detail=call.name,
                        payload={"ok": result.ok, "error": result.error, "args": call.arguments},
                    )
                )
                if failures >= 2:
                    break

            if reads:
                continue

            actions = [c for c in plan.tool_calls if c.name in ACTION_TOOLS]
            if not actions:
                break

            call = actions[0]
            expected = ACTION_FOR_INTENT.get(u.intent)
            if call.name not in {expected, "escalate_to_human", "create_support_ticket"}:
                trace.append(
                    TraceStep(
                        stage="guard",
                        detail="action_not_allowed_for_intent",
                        payload={"intent": u.intent, "action": call.name},
                    )
                )
                action_payload = {
                    "tool": call.name,
                    "ok": False,
                    "error": "ACTION_NOT_ALLOWED_FOR_INTENT",
                    "data": {},
                }
                action_reason = "ACTION_NOT_ALLOWED_FOR_INTENT"
            else:
                result = execute_tool(self.ctx, call)
                results.append(result)
                budget -= 1
                action_payload = {
                    "tool": call.name,
                    "ok": result.ok,
                    "error": result.error,
                    "data": result.data,
                }
                action_reason = "OK" if result.ok else result.error or "TOOL_FAILURE"
                trace.append(
                    TraceStep(
                        stage="action",
                        detail=call.name,
                        payload={
                            "ok": result.ok,
                            "error": result.error,
                            "data": result.data,
                            "args": call.arguments,
                        },
                    )
                )

                if result.ok:
                    verified, detail = self._verify(call.name, result.data)
                    trace.append(
                        TraceStep(
                            stage="verify",
                            detail="confirmed" if verified else "unconfirmed",
                            payload={"detail": detail},
                        )
                    )
                    if not verified:
                        action_payload["ok"] = False
                        action_payload["error"] = "UNVERIFIED_STATE"
                        action_reason = "UNVERIFIED_STATE"

            executed_action = True
            break

        # ---- failure ladder ----
        if failures >= 2 and action_payload is None:
            esc = execute_tool(
                self.ctx,
                ToolCall(
                    name="escalate_to_human",
                    arguments={
                        "reason": "backend_failure",
                        "summary": "Repeated tool failures while handling the request.",
                    },
                ),
            )
            results.append(esc)
            action_payload = {
                "tool": "escalate_to_human",
                "ok": esc.ok,
                "error": esc.error,
                "data": esc.data,
            }

        try:
            reply = _bounded(self.backend.respond, u, facts, action_payload)
        except BackendTimeout:
            trace.append(TraceStep(stage="respond", detail="timeout"))
            reply = FinalResponse(
                customer_message=(
                    "I'm sorry — I couldn't finish checking that in time, so I've passed this "
                    "to a colleague who can confirm the details."
                ),
                escalate=True,
                escalate_reason="backend_timeout",
            )

        if action_reason == "UNVERIFIED_STATE" and not reply.escalate:
            esc = execute_tool(
                self.ctx,
                ToolCall(
                    name="escalate_to_human",
                    arguments={
                        "reason": "state_unverified",
                        "summary": "Mutation could not be confirmed against stored state.",
                    },
                ),
            )
            results.append(esc)
            reply.escalate = True
            reply.escalate_reason = "state_unverified"

        if reply.escalate and not (action_payload or {}).get("tool") == "escalate_to_human":
            esc = execute_tool(
                self.ctx,
                ToolCall(
                    name="escalate_to_human",
                    arguments={
                        "reason": reply.escalate_reason or "model_escalation",
                        "summary": reply.customer_message[:500],
                    },
                ),
            )
            results.append(esc)

        decision = action_reason or ("ESCALATE" if reply.escalate else "ALLOW")
        eligibility = facts.get("check_return_eligibility") or {}
        if action_payload is None and eligibility.get("decision") not in (None, "ALLOW"):
            decision = str(eligibility.get("reason_code") or "DENY")
        order_error = (facts.get("get_order") or {}).get("error")
        if action_payload is None and order_error:
            decision = str(order_error)
        return self._finish(reply, u, action_payload, results, trace, started, decision)

    # -- internals ---------------------------------------------------------

    def _timeout_turn(self, started: float, trace: list[TraceStep], stage: str) -> TurnResult:
        """A backend that misses its budget escalates; it never gets to claim success."""
        trace.append(TraceStep(stage=stage, detail="timeout"))
        esc = execute_tool(
            self.ctx,
            ToolCall(
                name="escalate_to_human",
                arguments={
                    "reason": "backend_timeout",
                    "summary": f"Backend did not answer during {stage}.",
                },
            ),
        )
        reply = FinalResponse(
            customer_message=(
                "I'm sorry — I couldn't finish checking that in time, so I've passed this "
                "to a colleague who can confirm the details."
            ),
            escalate=True,
            escalate_reason="backend_timeout",
        )
        u = Understanding(intent="other", confidence=0.0)
        return self._finish(
            reply,
            u,
            {"tool": "escalate_to_human", "ok": esc.ok, "data": esc.data},
            [esc],
            trace,
            started,
            "ESCALATE",
        )

    def _history(self) -> list[dict[str, str]]:
        rows = list(
            self.s.scalars(
                select(Message)
                .where(Message.conversation_id == self.conversation_id)
                .order_by(Message.id.desc())
                .limit(10)
            )
        )
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    def _finish(
        self,
        reply: FinalResponse,
        u: Understanding,
        action: dict | None,
        results: list[ToolResult],
        trace: list[TraceStep],
        started: float,
        decision: str,
    ) -> TurnResult:
        self.s.add(
            Message(
                conversation_id=self.conversation_id,
                role="assistant",
                content=reply.customer_message,
            )
        )
        self.s.add(
            AuditLog(
                correlation_id=self.correlation_id,
                actor=f"customer:{self.customer_id}",
                action="turn",
                target=f"conversation:{self.conversation_id}",
                decision="ESCALATE" if reply.escalate else decision,
                reason_code=decision,
                detail=(
                    f"intent={u.intent}; action={(action or {}).get('tool')}; "
                    f"model={getattr(self.backend, 'model_id', 'unknown')}"
                ),
            )
        )
        self.s.commit()
        latency = int((time.perf_counter() - started) * 1000)
        return TurnResult(
            conversation_id=self.conversation_id,
            message=reply.customer_message,
            intent=u.intent,
            action_taken=(action or {}).get("tool") if (action or {}).get("ok") else None,
            action_reference=(
                (action or {}).get("data", {}).get("case_reference")
                or (action or {}).get("data", {}).get("label_code")
                or (
                    f"REF-{int((action or {}).get('data', {}).get('refund_id')):04d}"
                    if (action or {}).get("data", {}).get("refund_id")
                    else None
                )
                or (
                    f"TKT-{int((action or {}).get('data', {}).get('ticket_id'))}"
                    if (action or {}).get("data", {}).get("ticket_id")
                    else None
                )
            ),
            escalated=reply.escalate or decision == "ESCALATE",
            reason_code=decision,
            tool_calls=results,
            trace=trace,
            latency_ms=latency,
            model_id=getattr(self.backend, "model_id", "unknown"),
        )

    def _verify(self, tool: str, data: dict) -> tuple[bool, str]:
        """Confirm the mutation is actually persisted before the customer is told it happened."""
        try:
            if tool == "create_return_request":
                req = self.s.get(ReturnRequest, data.get("return_request_id"))
                label = self.s.scalar(
                    select(ReturnLabel).where(
                        ReturnLabel.return_request_id == (req.id if req else -1)
                    )
                )
                return bool(
                    req and label and req.status == "created"
                ), f"return={bool(req)} label={bool(label)}"
            if tool == "create_replacement_request":
                req = self.s.get(ReplacementRequest, data.get("replacement_request_id"))
                return bool(req and req.status == "created"), f"replacement={bool(req)}"
            if tool == "request_cancellation":
                order = self.s.get(Order, data.get("order_id"))
                refund = self.s.get(Refund, data.get("refund_id"))
                return bool(order and order.status == "cancelled" and refund), "cancelled+refund"
            if tool == "submit_refund_request":
                refund = self.s.get(Refund, data.get("refund_id"))
                if not refund:
                    return False, "refund row missing"
                if data.get("status") == "pending_approval":
                    approval = self.s.scalar(
                        select(Approval).where(Approval.refund_id == refund.id)
                    )
                    return bool(approval and refund.status == "pending_approval"), "approval row"
                return refund.status in {"processed", "approved"}, f"refund status={refund.status}"
            if tool == "escalate_to_human":
                esc = self.s.get(Escalation, data.get("escalation_id"))
                return bool(esc), f"escalation={bool(esc)}"
            if tool == "create_support_ticket":
                ticket = self.s.get(Ticket, data.get("ticket_id"))
                return bool(ticket), f"ticket={bool(ticket)}"
        except Exception as exc:  # noqa: BLE001
            return False, type(exc).__name__
        return True, "no verification required"

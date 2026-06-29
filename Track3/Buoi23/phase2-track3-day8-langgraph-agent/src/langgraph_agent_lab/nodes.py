"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os
import time
from typing import Literal

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── classification structured-output schema ─────────────────────────
class Classification(BaseModel):
    """Schema the LLM is forced to fill via .with_structured_output()."""

    route: Literal["simple", "tool", "missing_info", "risky", "error"] = Field(
        description="The single best route for this support ticket."
    )
    reasoning: str = Field(default="", description="One short sentence justifying the route.")


_CLASSIFY_SYSTEM = """You are an intent router for a customer-support agent.
Classify the user's ticket into EXACTLY ONE route. Apply this priority order
(higher wins when a ticket could fit several):

1. risky  — actions with side effects: refunds, deletions, cancellations,
            sending emails, account changes, anything destructive or irreversible.
2. tool   — information lookups that need a system call: order status, tracking,
            account/record search, "look up ...".
3. missing_info — vague/incomplete tickets with no actionable subject
            (e.g. "can you fix it?", "help", "it's broken").
4. error  — reports of system failures: timeouts, crashes, "cannot recover",
            service unavailable, exceptions while processing.
5. simple — general questions answerable directly without tools or actions
            (e.g. "how do I reset my password?").

Return only the structured route."""


def _classify_with_llm(query: str) -> Classification:
    """Run the LLM classifier with structured output."""
    llm = get_llm()
    structured = llm.with_structured_output(Classification)
    prompt = f"{_CLASSIFY_SYSTEM}\n\nTicket:\n\"\"\"\n{query}\n\"\"\""
    result = structured.invoke(prompt)
    if isinstance(result, Classification):
        return result
    # Some providers return a dict — coerce defensively.
    return Classification.model_validate(result)


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM (structured output)."""
    start = time.perf_counter()
    query = state.get("query", "")
    classification = _classify_with_llm(query)
    route = classification.route
    risk_level = "high" if route == "risky" else "low"
    latency_ms = int((time.perf_counter() - start) * 1000)
    return {
        "route": route,
        "risk_level": risk_level,
        "messages": [f"classify:{route}"],
        "events": [
            make_event(
                "classify",
                "completed",
                f"routed to {route}",
                route=route,
                risk_level=risk_level,
                reasoning=classification.reasoning,
                latency_ms=latency_ms,
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call, simulating transient failures on the error route.

    The error route must fail its first couple of attempts so the retry loop is
    exercised; every other route (and later error attempts) succeeds.
    """
    route = state.get("route", "")
    attempt = state.get("attempt", 0)
    query = state.get("query", "")

    if route == "error" and attempt < 2:
        result = f"ERROR: transient tool failure on attempt {attempt} for '{query[:40]}'"
        event = make_event("tool", "error", "tool call failed (transient)", attempt=attempt)
    else:
        result = f"TOOL_OK: result for '{query[:60]}' (attempt {attempt})"
        event = make_event("tool", "completed", "tool call succeeded", attempt=attempt)

    return {
        "tool_results": [result],
        "messages": [f"tool:{'error' if result.startswith('ERROR') else 'ok'}"],
        "events": [event],
    }


class _Judgement(BaseModel):
    satisfactory: bool = Field(description="True if the tool result answers the request.")
    score: int = Field(default=3, ge=1, le=5, description="Quality score 1-5.")


def evaluate_node(state: AgentState) -> dict:
    """Evaluate the latest tool result — the retry-loop gate.

    The retry decision is driven by a deterministic check (presence of "ERROR")
    so the loop is reliable and bounded. When the result looks fine we ALSO run
    an LLM-as-judge pass (bonus) to score quality; that score is recorded in the
    event metadata but never overrides the deterministic gate.
    """
    tool_results = state.get("tool_results", []) or []
    latest = tool_results[-1] if tool_results else ""

    if "ERROR" in latest.upper():
        return {
            "evaluation_result": "needs_retry",
            "messages": ["evaluate:needs_retry"],
            "events": [make_event("evaluate", "needs_retry", "tool result failed check")],
        }

    # Result looks good — confirm with an LLM-as-judge (best effort).
    score = None
    judge_note = "heuristic: no error marker"
    try:
        llm = get_llm()
        judge = llm.with_structured_output(_Judgement)
        verdict = judge.invoke(
            "You are a QA judge. Given a user request and a tool result, decide if the "
            "result is satisfactory and score its quality 1-5.\n"
            f"Request: {state.get('query', '')}\nTool result: {latest}"
        )
        if not isinstance(verdict, _Judgement):
            verdict = _Judgement.model_validate(verdict)
        score = verdict.score
        judge_note = f"llm-judge: satisfactory={verdict.satisfactory} score={verdict.score}"
    except Exception as exc:  # noqa: BLE001 — judge is optional, never break the gate
        judge_note = f"llm-judge skipped: {exc}"

    return {
        "evaluation_result": "success",
        "messages": ["evaluate:success"],
        "events": [make_event("evaluate", "success", judge_note, score=score)],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM, grounded in available context."""
    start = time.perf_counter()
    query = state.get("query", "")
    tool_results = state.get("tool_results", []) or []
    approval = state.get("approval")

    context_parts = [f"User request: {query}"]
    if tool_results:
        context_parts.append("Tool results:\n" + "\n".join(f"- {r}" for r in tool_results))
    if approval:
        context_parts.append(
            f"Approval decision: approved={approval.get('approved')} "
            f"by {approval.get('reviewer')} ({approval.get('comment')})"
        )
    context = "\n\n".join(context_parts)

    prompt = (
        "You are a helpful customer-support agent. Write a concise, friendly reply to the "
        "user. Ground every claim ONLY in the context below — do not invent order numbers, "
        "amounts, or facts that are not present. If a tool result is shown, summarise it.\n\n"
        f"{context}\n\nReply:"
    )
    llm = get_llm()
    response = llm.invoke(prompt)
    answer = getattr(response, "content", str(response))
    latency_ms = int((time.perf_counter() - start) * 1000)

    return {
        "final_answer": answer,
        "messages": ["answer:generated"],
        "events": [
            make_event("answer", "completed", "grounded answer generated", latency_ms=latency_ms)
        ],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    Uses the LLM to craft a specific question; falls back to a generic prompt if
    the LLM is unavailable so the route always terminates with an answer.
    """
    query = state.get("query", "")
    question = ""
    try:
        llm = get_llm()
        resp = llm.invoke(
            "The user's support ticket is too vague to act on. Ask ONE specific, polite "
            "clarifying question to get the missing detail you need (e.g. order id, what "
            f"exactly is broken, desired outcome).\nTicket: {query}\nQuestion:"
        )
        question = getattr(resp, "content", str(resp)).strip()
    except Exception:  # noqa: BLE001 — never let clarification fail the graph
        question = ""
    if not question:
        question = (
            "Could you share a bit more detail — what exactly is happening and which "
            "order or account does it concern?"
        )
    return {
        "pending_question": question,
        "final_answer": question,
        "messages": ["clarify:asked"],
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval."""
    query = state.get("query", "")
    proposed = (
        f"Proposed high-risk action for ticket: '{query}'. "
        "Requires human approval before execution."
    )
    return {
        "proposed_action": proposed,
        "risk_level": "high",
        "messages": ["risky:proposed"],
        "events": [
            make_event(
                "risky_action", "completed", "risky action prepared", proposed_action=proposed
            )
        ],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default: mock approval (approved=True) so CI/tests run offline.
    Extension: with LANGGRAPH_INTERRUPT=true, pause the graph via interrupt() and
    resume with the reviewer's real decision.
    """
    proposed = state.get("proposed_action", "")
    decision = {"approved": True, "reviewer": "mock-reviewer", "comment": "auto-approved (mock)"}

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        human = interrupt(
            {"proposed_action": proposed, "question": "Approve this action? (yes/no)"}
        )
        # On resume, `human` carries whatever the caller passed to Command(resume=...).
        if isinstance(human, dict):
            decision = {
                "approved": bool(human.get("approved", True)),
                "reviewer": human.get("reviewer", "human-reviewer"),
                "comment": human.get("comment", ""),
            }
        elif isinstance(human, str):
            approved = human.strip().lower() in {"yes", "y", "approve", "approved", "true"}
            decision = {"approved": approved, "reviewer": "human-reviewer", "comment": human}

    return {
        "approval": decision,
        "messages": [f"approval:{'approved' if decision['approved'] else 'rejected'}"],
        "events": [
            make_event(
                "approval",
                "completed",
                f"approval decision: {decision['approved']}",
                approved=decision["approved"],
                reviewer=decision["reviewer"],
            )
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt: bump the counter and log the transient failure."""
    attempt = state.get("attempt", 0) + 1
    msg = f"retry attempt {attempt} after transient failure"
    return {
        "attempt": attempt,
        "errors": [msg],
        "messages": [f"retry:{attempt}"],
        "events": [make_event("retry", "completed", msg, attempt=attempt)],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries (third layer of defence)."""
    attempts = state.get("attempt", 0)
    answer = (
        "We're sorry — we couldn't complete your request automatically after "
        f"{attempts} attempt(s). It has been escalated to a human agent who will follow up."
    )
    return {
        "final_answer": answer,
        "messages": ["dead_letter:escalated"],
        "events": [
            make_event(
                "dead_letter", "completed", "max retries exceeded; escalated", attempts=attempts
            )
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {
        "messages": ["finalize:done"],
        "events": [
            make_event("finalize", "completed", "workflow finished", route=state.get("route", ""))
        ],
    }

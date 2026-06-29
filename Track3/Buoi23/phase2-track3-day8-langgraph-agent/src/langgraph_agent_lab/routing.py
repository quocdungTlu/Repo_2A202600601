"""Routing functions for conditional edges.

Each function takes AgentState and returns a string — the name of the next node.
These strings MUST match node names registered in graph.py.
"""

from __future__ import annotations

from .state import AgentState

# Single source of truth for classify → next-node mapping. Unknown routes fall
# back to "answer" so a misbehaving LLM still terminates the graph gracefully.
_CLASSIFY_NEXT = {
    "simple": "answer",
    "tool": "tool",
    "missing_info": "clarify",
    "risky": "risky_action",
    "error": "retry",
}


def route_after_classify(state: AgentState) -> str:
    """Map classified route to the next graph node."""
    return _CLASSIFY_NEXT.get(state.get("route", ""), "answer")


def route_after_evaluate(state: AgentState) -> str:
    """Decide if tool result is satisfactory or needs retry.

    This is the 'done?' check that creates the retry loop —
    a key LangGraph advantage over linear LCEL chains.
    """
    if state.get("evaluation_result") == "needs_retry":
        return "retry"
    return "answer"


def route_after_retry(state: AgentState) -> str:
    """Decide whether to retry the tool or give up.

    Bounded: once the attempt counter reaches max_attempts we escalate to the
    dead-letter node instead of looping forever.
    """
    if state.get("attempt", 0) < state.get("max_attempts", 3):
        return "tool"
    return "dead_letter"


def route_after_approval(state: AgentState) -> str:
    """Route based on human approval decision."""
    approval = state.get("approval") or {}
    if approval.get("approved"):
        return "tool"
    return "clarify"

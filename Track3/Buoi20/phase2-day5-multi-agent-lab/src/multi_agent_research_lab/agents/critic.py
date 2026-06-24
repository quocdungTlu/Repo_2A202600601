"""Optional critic agent: fact-check / citation-coverage review (bonus)."""

from __future__ import annotations

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.metrics import citation_coverage
from multi_agent_research_lab.observability.tracing import trace_span


class CriticAgent(BaseAgent):
    """Fact-checking and citation-coverage review of the final answer."""

    name = "critic"

    # Below this coverage we record a guardrail warning instead of silently passing.
    min_coverage: float = 0.5

    def run(self, state: ResearchState) -> ResearchState:
        with trace_span("critic", {}) as span:
            answer = state.final_answer or ""
            coverage = citation_coverage(answer, state.sources)
            grounded = bool(state.sources) and coverage >= self.min_coverage
            findings = [
                f"citation_coverage={coverage:.2f}",
                f"sources={len(state.sources)}",
                "PASS" if grounded else "WARN: low citation coverage / ungrounded claims",
            ]
            if not grounded:
                state.errors.append("critic: low citation coverage")
            span["attributes"]["coverage"] = coverage

        state.agent_results.append(
            AgentResult(
                agent=AgentName.CRITIC,
                content=" | ".join(findings),
                metadata={"citation_coverage": coverage, "grounded": grounded},
            )
        )
        state.add_trace_event("critic.done", {"coverage": coverage, "grounded": grounded})
        return state

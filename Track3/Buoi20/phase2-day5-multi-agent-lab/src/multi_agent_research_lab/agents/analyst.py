"""Analyst agent: turns research notes into structured insights."""

from __future__ import annotations

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient

_SYSTEM = (
    "[role:analyst] You are an analysis agent. Extract the key claims from the research notes, "
    "compare viewpoints, and flag any claim that lacks a supporting source as weak evidence."
)


class AnalystAgent(BaseAgent):
    """Turns research notes into structured insights."""

    name = "analyst"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        notes = state.research_notes or "No research notes available."
        with trace_span("analyst", {"has_notes": state.research_notes is not None}) as span:
            user = f"Question: {state.request.query}\n\nResearch notes:\n{notes}"
            resp = self.llm.complete(_SYSTEM, user)
            state.analysis_notes = resp.content
            span["attributes"]["cost_usd"] = resp.cost_usd

        state.agent_results.append(
            AgentResult(
                agent=AgentName.ANALYST,
                content=resp.content,
                metadata={
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "cost_usd": resp.cost_usd,
                },
            )
        )
        state.add_trace_event("analyst.done", {"cost_usd": resp.cost_usd})
        return state

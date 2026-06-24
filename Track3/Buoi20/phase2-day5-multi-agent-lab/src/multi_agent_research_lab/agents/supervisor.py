"""Supervisor / router: decides the next worker and the stop condition."""

from __future__ import annotations

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState

# Possible routing decisions.
RESEARCHER = "researcher"
ANALYST = "analyst"
WRITER = "writer"
DONE = "done"


class SupervisorAgent(BaseAgent):
    """Decides which worker should run next and when to stop.

    Routing is a deterministic policy over the shared state:

    1. Stop if the max-iteration guardrail is hit (prevents infinite loops).
    2. Stop and fall back if too many agent errors have accumulated.
    3. Otherwise fill the first missing stage: research -> analysis -> writing.
    """

    name = "supervisor"

    # If errors reach this count we stop early and let the writer produce a best-effort answer.
    max_errors: int = 2

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def decide(self, state: ResearchState) -> str:
        """Pure routing function returning one of: researcher, analyst, writer, done."""

        if state.iteration >= self.settings.max_iterations:
            return DONE
        if len(state.errors) >= self.max_errors:
            # Failure fallback: if we have anything, let the writer wrap up; else give up.
            return WRITER if state.final_answer is None and state.research_notes else DONE
        if not state.research_notes:
            return RESEARCHER
        if not state.analysis_notes:
            return ANALYST
        if not state.final_answer:
            return WRITER
        return DONE

    def run(self, state: ResearchState) -> ResearchState:
        """Record the routing decision on the shared state and return it."""

        decision = self.decide(state)
        state.add_trace_event("supervisor.route", {"next": decision, "iteration": state.iteration})
        state.agent_results.append(
            AgentResult(
                agent=AgentName.SUPERVISOR,
                content=f"route -> {decision}",
                metadata={"iteration": state.iteration, "errors": len(state.errors)},
            )
        )
        return state

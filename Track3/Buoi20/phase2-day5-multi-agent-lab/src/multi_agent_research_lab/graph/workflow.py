"""LangGraph workflow: wires the supervisor + worker agents into a directed graph."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import (
    ANALYST,
    DONE,
    RESEARCHER,
    WRITER,
    SupervisorAgent,
)
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.state import ResearchState

# Node names used in the graph.
_SUPERVISOR = "supervisor"
_RESEARCHER = "researcher"
_ANALYST = "analyst"
_WRITER = "writer"
_CRITIC = "critic"


class MultiAgentWorkflow:
    """Builds and runs the multi-agent LangGraph.

    Graph topology:
        START -> supervisor
        supervisor --(route)--> researcher | analyst | writer | END
        researcher -> supervisor
        analyst    -> supervisor
        writer     -> critic -> END
    """

    def __init__(self, settings: Settings | None = None, use_critic: bool = True) -> None:
        self.settings = settings or get_settings()
        self.supervisor = SupervisorAgent(settings=self.settings)
        self.researcher = ResearcherAgent()
        self.analyst = AnalystAgent()
        self.writer = WriterAgent()
        self.critic = CriticAgent()
        self.use_critic = use_critic
        self._graph = self.build()

    # ------------------------------------------------------------------ build
    def build(self) -> Any:
        """Create and compile the LangGraph state graph."""

        graph: StateGraph = StateGraph(dict)

        # Adapter: LangGraph passes/returns dict; our agents use ResearchState.
        def _wrap(fn):  # type: ignore[no-untyped-def]
            def node(state_dict: dict) -> dict:  # type: ignore[type-arg]
                state = ResearchState.model_validate(state_dict)
                updated = fn(state)
                state.record_route(updated.route_history[-1] if updated.route_history else "?")
                return updated.model_dump()

            return node

        def supervisor_node(state_dict: dict) -> dict:  # type: ignore[type-arg]
            state = ResearchState.model_validate(state_dict)
            decision = self.supervisor.decide(state)
            state.add_trace_event("supervisor.route", {"next": decision, "iteration": state.iteration})
            state.record_route(decision)
            return state.model_dump()

        def researcher_node(state_dict: dict) -> dict:  # type: ignore[type-arg]
            state = ResearchState.model_validate(state_dict)
            state = self.researcher.run(state)
            return state.model_dump()

        def analyst_node(state_dict: dict) -> dict:  # type: ignore[type-arg]
            state = ResearchState.model_validate(state_dict)
            state = self.analyst.run(state)
            return state.model_dump()

        def writer_node(state_dict: dict) -> dict:  # type: ignore[type-arg]
            state = ResearchState.model_validate(state_dict)
            state = self.writer.run(state)
            return state.model_dump()

        def critic_node(state_dict: dict) -> dict:  # type: ignore[type-arg]
            state = ResearchState.model_validate(state_dict)
            state = self.critic.run(state)
            return state.model_dump()

        # Routing function for conditional edges out of supervisor.
        def _route(state_dict: dict) -> str:  # type: ignore[type-arg]
            history = state_dict.get("route_history", [])
            last = history[-1] if history else DONE
            if last == RESEARCHER:
                return _RESEARCHER
            if last == ANALYST:
                return _ANALYST
            if last == WRITER:
                return _WRITER
            return END  # type: ignore[return-value]

        graph.add_node(_SUPERVISOR, supervisor_node)
        graph.add_node(_RESEARCHER, researcher_node)
        graph.add_node(_ANALYST, analyst_node)
        graph.add_node(_WRITER, writer_node)
        if self.use_critic:
            graph.add_node(_CRITIC, critic_node)

        graph.set_entry_point(_SUPERVISOR)
        graph.add_conditional_edges(
            _SUPERVISOR,
            _route,
            {
                _RESEARCHER: _RESEARCHER,
                _ANALYST: _ANALYST,
                _WRITER: _WRITER,
                END: END,
            },
        )

        # Workers loop back to supervisor so the routing policy sees updated state.
        graph.add_edge(_RESEARCHER, _SUPERVISOR)
        graph.add_edge(_ANALYST, _SUPERVISOR)

        if self.use_critic:
            graph.add_edge(_WRITER, _CRITIC)
            graph.add_edge(_CRITIC, END)
        else:
            graph.add_edge(_WRITER, END)

        return graph.compile()

    # ------------------------------------------------------------------ run
    def run(self, state: ResearchState) -> ResearchState:
        """Execute the compiled graph and return the final ResearchState."""

        result_dict = self._graph.invoke(state.model_dump())
        return ResearchState.model_validate(result_dict)

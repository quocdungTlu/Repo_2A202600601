"""Tests that verify the implemented agents behave correctly (not just skeleton stubs)."""

from multi_agent_research_lab.agents import SupervisorAgent
from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState


def test_supervisor_routes_to_researcher_when_no_notes() -> None:
    """Fresh state → supervisor should route to researcher first."""

    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    decision = SupervisorAgent().decide(state)
    assert decision == "researcher"


def test_supervisor_routes_to_done_at_max_iterations() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    for _ in range(6):
        state.record_route("researcher")
    decision = SupervisorAgent().decide(state)
    assert decision == "done"


def test_supervisor_routes_to_analyst_after_research() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    state.research_notes = "Some research."
    decision = SupervisorAgent().decide(state)
    assert decision == "analyst"


def test_supervisor_routes_to_writer_after_analysis() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    state.research_notes = "Some research."
    state.analysis_notes = "Some analysis."
    decision = SupervisorAgent().decide(state)
    assert decision == "writer"


def test_supervisor_done_when_all_fields_filled() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    state.research_notes = "Research done."
    state.analysis_notes = "Analysis done."
    state.final_answer = "Final answer."
    decision = SupervisorAgent().decide(state)
    assert decision == "done"

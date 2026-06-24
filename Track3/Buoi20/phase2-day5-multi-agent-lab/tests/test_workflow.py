"""End-to-end test for the multi-agent workflow (offline mock)."""

from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow


def test_workflow_produces_final_answer() -> None:
    state = ResearchState(request=ResearchQuery(query="Research GraphRAG state-of-the-art"))
    result = MultiAgentWorkflow().run(state)
    assert result.final_answer is not None
    assert len(result.final_answer) > 20


def test_workflow_populates_all_stages() -> None:
    state = ResearchState(request=ResearchQuery(query="Compare single-agent and multi-agent for customer support"))
    result = MultiAgentWorkflow().run(state)
    assert result.research_notes is not None
    assert result.analysis_notes is not None
    assert result.final_answer is not None
    assert result.sources


def test_workflow_no_errors_for_happy_path() -> None:
    state = ResearchState(request=ResearchQuery(query="Summarize production guardrails for LLM agents"))
    result = MultiAgentWorkflow().run(state)
    # Critic may flag low coverage in mock mode but should not hard-error
    assert result.final_answer is not None


def test_workflow_route_history() -> None:
    state = ResearchState(request=ResearchQuery(query="What is GraphRAG?"))
    result = MultiAgentWorkflow().run(state)
    assert "researcher" in result.route_history
    assert "analyst" in result.route_history
    assert "writer" in result.route_history

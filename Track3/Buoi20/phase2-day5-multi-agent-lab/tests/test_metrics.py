"""Tests for offline quality metrics."""

from multi_agent_research_lab.core.schemas import ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.metrics import (
    citation_coverage,
    quality_score,
    split_claims,
    total_cost_usd,
)


def test_citation_coverage_with_indices() -> None:
    sources = [SourceDocument(title="GraphRAG Paper", url="https://example.org", snippet="...")]
    answer = "GraphRAG improves multi-hop reasoning [1]. Another claim."
    cov = citation_coverage(answer, sources)
    assert 0.0 < cov <= 1.0


def test_citation_coverage_zero_when_no_sources() -> None:
    cov = citation_coverage("Some answer without refs.", [])
    assert cov == 0.0


def test_quality_score_increases_with_stages() -> None:
    state = ResearchState(request=ResearchQuery(query="Test query 123"))
    q0 = quality_score(state)
    state.research_notes = "Some research."
    q1 = quality_score(state)
    state.analysis_notes = "Some analysis."
    q2 = quality_score(state)
    assert q0 < q1 < q2


def test_total_cost_usd_zero_when_no_results() -> None:
    state = ResearchState(request=ResearchQuery(query="Test query 123"))
    assert total_cost_usd(state) == 0.0


def test_split_claims_ignores_references_block() -> None:
    text = "First claim. Second claim.\n\n## References\n[1] source"
    claims = split_claims(text)
    assert all("References" not in c and "[1]" not in c for c in claims)

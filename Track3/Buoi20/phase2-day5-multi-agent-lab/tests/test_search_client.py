"""Tests for the SearchClient mock backend."""

from multi_agent_research_lab.services.search_client import SearchClient


def test_mock_returns_relevant_docs() -> None:
    client = SearchClient()
    assert client.is_mock
    docs = client.search("graphrag knowledge graph")
    assert docs
    assert any("GraphRAG" in d.title for d in docs)


def test_mock_respects_max_results() -> None:
    client = SearchClient()
    docs = client.search("agent workflow", max_results=2)
    assert len(docs) <= 2


def test_mock_returns_empty_for_no_match() -> None:
    client = SearchClient()
    docs = client.search("xyzzy banana frango")
    assert docs == []


def test_mock_is_deterministic() -> None:
    client = SearchClient()
    d1 = client.search("guardrails production")
    d2 = client.search("guardrails production")
    assert [d.title for d in d1] == [d.title for d in d2]

"""Tests for the LLMClient mock backend."""

from multi_agent_research_lab.services.llm_client import LLMClient, _approx_tokens


def test_mock_returns_deterministic_output() -> None:
    client = LLMClient()
    assert client.is_mock
    r1 = client.complete("system prompt", "user prompt")
    r2 = client.complete("system prompt", "user prompt")
    assert r1.content == r2.content


def test_mock_tokens_and_cost_populated() -> None:
    client = LLMClient()
    resp = client.complete("system", "What is multi-agent?")
    assert resp.input_tokens > 0
    assert resp.output_tokens > 0
    assert resp.cost_usd > 0


def test_role_tag_shapes_output() -> None:
    client = LLMClient()
    researcher_resp = client.complete("[role:researcher] Research notes.", "graphrag")
    writer_resp = client.complete("[role:writer] Write clearly.", "graphrag")
    assert "Research summary" in researcher_resp.content
    assert "References" in writer_resp.content or "cited" in writer_resp.content.lower()


def test_approx_tokens_reasonable() -> None:
    assert _approx_tokens("hello world") == 3
    assert _approx_tokens("") == 1

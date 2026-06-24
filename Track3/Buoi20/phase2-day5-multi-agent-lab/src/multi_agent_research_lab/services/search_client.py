"""Search client abstraction for ResearcherAgent.

Default backend is a small, deterministic in-repo corpus so the lab runs offline and
benchmarks are reproducible. Switch to Tavily by setting ``OFFLINE_MODE=false`` and a key.
"""

from __future__ import annotations

import re

from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import SourceDocument

# Minimal curated corpus. Each entry stands in for a retrieved web/document chunk.
_CORPUS: list[dict[str, str]] = [
    {
        "title": "GraphRAG: graph-structured retrieval for LLMs",
        "url": "https://example.org/graphrag",
        "snippet": (
            "GraphRAG builds a knowledge graph from a corpus and uses community summaries to "
            "answer global questions that flat vector RAG misses, improving multi-hop reasoning."
        ),
        "tags": "graphrag rag retrieval graph knowledge multi-hop reasoning summary state-of-the-art",
    },
    {
        "title": "Vector RAG baselines and their limits",
        "url": "https://example.org/vector-rag",
        "snippet": (
            "Flat vector RAG retrieves top-k chunks by embedding similarity. It is strong for local "
            "fact lookup but weak on questions that require aggregating across many documents."
        ),
        "tags": "rag vector embedding retrieval baseline chunk similarity summary",
    },
    {
        "title": "Multi-agent LLM systems: supervisor-worker patterns",
        "url": "https://example.org/multi-agent",
        "snippet": (
            "A supervisor routes tasks to specialised worker agents (researcher, analyst, writer). "
            "This decomposition improves quality on complex tasks at the cost of latency and tokens."
        ),
        "tags": "multi-agent supervisor worker routing orchestration agent decomposition latency workflow",
    },
    {
        "title": "Single-agent vs multi-agent trade-offs",
        "url": "https://example.org/single-vs-multi",
        "snippet": (
            "Single agents are cheaper and lower-latency for narrow tasks. Multi-agent workflows win "
            "when a task has distinct sub-skills, needs review, or benefits from parallel exploration."
        ),
        "tags": "single-agent multi-agent comparison cost latency quality customer support trade-off workflow",
    },
    {
        "title": "Production guardrails for LLM agents",
        "url": "https://example.org/guardrails",
        "snippet": (
            "Core guardrails include max-iteration caps, timeouts, retries with fallback, input/output "
            "validation, and human-in-the-loop review for high-risk actions."
        ),
        "tags": "guardrails production max iterations timeout retry fallback validation hitl safety agent summarize",
    },
    {
        "title": "Evaluating agent workflows with benchmarks",
        "url": "https://example.org/agent-eval",
        "snippet": (
            "Benchmark agents on latency, token cost, answer quality (rubric), citation coverage, and "
            "failure rate. Compare against a single-agent baseline to justify added complexity."
        ),
        "tags": "benchmark evaluation latency cost quality citation coverage failure rate baseline metric",
    },
    {
        "title": "Citations and grounding in RAG answers",
        "url": "https://example.org/citations",
        "snippet": (
            "Grounded answers attach a source to every non-trivial claim. Citation coverage is the share "
            "of claims with a traceable source and is a key signal for hallucination risk."
        ),
        "tags": "citation grounding source claim hallucination coverage rag answer trust summary",
    },
    {
        "title": "Customer support automation with LLM agents",
        "url": "https://example.org/support-agents",
        "snippet": (
            "For customer support, multi-agent setups separate intent triage, knowledge lookup, and reply "
            "drafting; single agents suffice for FAQ-style flows with low ambiguity."
        ),
        "tags": "customer support agent triage intent reply faq automation multi-agent single-agent workflow",
    },
]

_STOP = {"the", "and", "for", "with", "from", "that", "this", "what", "how", "are", "a", "an", "of", "to", "in", "on"}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9-]+", text.lower()) if w not in _STOP and len(w) > 2}


class SearchClient:
    """Provider-agnostic search client. Offline backend = curated local corpus."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_mock(self) -> bool:
        return self.settings.use_mock_search

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        """Return documents relevant to a query, highest score first."""

        if not self.is_mock:
            return self._tavily_search(query, max_results)
        return self._mock_search(query, max_results)

    def _mock_search(self, query: str, max_results: int) -> list[SourceDocument]:
        q = _tokens(query)
        scored: list[tuple[int, dict[str, str]]] = []
        for doc in _CORPUS:
            haystack = _tokens(doc["title"] + " " + doc["snippet"] + " " + doc["tags"])
            score = len(q & haystack)
            if score:
                scored.append((score, doc))
        # deterministic: sort by score desc, then title for stable ties
        scored.sort(key=lambda x: (-x[0], x[1]["title"]))
        return [
            SourceDocument(
                title=doc["title"],
                url=doc["url"],
                snippet=doc["snippet"],
                metadata={"relevance": score, "backend": "mock-corpus"},
            )
            for score, doc in scored[:max_results]
        ]

    def _tavily_search(self, query: str, max_results: int) -> list[SourceDocument]:
        from tavily import TavilyClient  # lazy import

        client = TavilyClient(api_key=self.settings.tavily_api_key)
        resp = client.search(query=query, max_results=max_results)
        return [
            SourceDocument(
                title=item.get("title", "untitled"),
                url=item.get("url"),
                snippet=item.get("content", ""),
                metadata={"score": item.get("score"), "backend": "tavily"},
            )
            for item in resp.get("results", [])
        ]

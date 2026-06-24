"""Researcher agent: gathers sources and writes concise, cited research notes."""

from __future__ import annotations

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.search_client import SearchClient

_SYSTEM = (
    "[role:researcher] You are a research agent. Read the retrieved sources and produce "
    "concise notes. Every note must reference a source by its [n] index. Do not invent facts."
)


class ResearcherAgent(BaseAgent):
    """Collects sources and creates concise research notes."""

    name = "researcher"

    def __init__(self, search: SearchClient | None = None, llm: LLMClient | None = None) -> None:
        self.search = search or SearchClient()
        self.llm = llm or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        with trace_span("researcher", {"query": state.request.query}) as span:
            sources = self.search.search(state.request.query, max_results=state.request.max_sources)
            state.sources = sources

            numbered = "\n".join(
                f"[{i + 1}] {s.title} — {s.snippet}" for i, s in enumerate(sources)
            ) or "No sources retrieved."
            user = f"Question: {state.request.query}\n\nRetrieved sources:\n{numbered}"
            resp = self.llm.complete(_SYSTEM, user)
            state.research_notes = resp.content

            span["attributes"]["sources"] = len(sources)
            span["attributes"]["cost_usd"] = resp.cost_usd

        state.agent_results.append(
            AgentResult(
                agent=AgentName.RESEARCHER,
                content=resp.content,
                metadata={
                    "sources": len(sources),
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "cost_usd": resp.cost_usd,
                },
            )
        )
        state.add_trace_event("researcher.done", {"sources": len(sources), "cost_usd": resp.cost_usd})
        return state

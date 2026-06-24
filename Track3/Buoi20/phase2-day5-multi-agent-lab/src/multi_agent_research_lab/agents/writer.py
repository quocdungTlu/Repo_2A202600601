"""Writer agent: synthesises the final, cited answer."""

from __future__ import annotations

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient

_SYSTEM = (
    "[role:writer] You are a writing agent. Synthesise a clear answer for the target audience "
    "using the analysis and research notes. Keep claims grounded in the listed sources."
)


class WriterAgent(BaseAgent):
    """Produces final answer from research and analysis notes."""

    name = "writer"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        with trace_span("writer", {"audience": state.request.audience}) as span:
            user = (
                f"Question: {state.request.query}\n"
                f"Audience: {state.request.audience}\n\n"
                f"Analysis notes:\n{state.analysis_notes or '(none)'}\n\n"
                f"Research notes:\n{state.research_notes or '(none)'}"
            )
            resp = self.llm.complete(_SYSTEM, user)
            answer = resp.content
            if state.sources:
                refs = "\n".join(
                    f"[{i + 1}] {s.title}" + (f" — {s.url}" if s.url else "")
                    for i, s in enumerate(state.sources)
                )
                answer = f"{answer}\n\n## References\n{refs}"
            state.final_answer = answer
            span["attributes"]["cost_usd"] = resp.cost_usd

        state.agent_results.append(
            AgentResult(
                agent=AgentName.WRITER,
                content=answer,
                metadata={
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "cost_usd": resp.cost_usd,
                },
            )
        )
        state.add_trace_event("writer.done", {"cost_usd": resp.cost_usd})
        return state

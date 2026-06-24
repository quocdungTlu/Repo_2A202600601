"""Command-line entrypoint for the lab."""

from __future__ import annotations

from time import perf_counter
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.schemas import BenchmarkMetrics, ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.benchmark import run_benchmark
from multi_agent_research_lab.evaluation.metrics import quality_score, total_cost_usd, total_tokens
from multi_agent_research_lab.evaluation.report import render_markdown_report
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.logging import configure_logging
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.storage import LocalArtifactStore

app = typer.Typer(help="Multi-Agent Research Lab CLI")
console = Console()


def _init() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


@app.command()
def baseline(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run a single-agent baseline (one LLM call, no decomposition)."""

    _init()
    llm = LLMClient()
    t0 = perf_counter()
    resp = llm.complete(
        "[role:assistant] You are a research assistant. Answer the question as completely as possible.",
        query,
    )
    latency = perf_counter() - t0

    state = ResearchState(request=ResearchQuery(query=query))
    state.final_answer = resp.content
    state.research_notes = resp.content

    q = quality_score(state)
    console.print(Panel.fit(resp.content, title="Single-Agent Baseline"))
    console.print(
        f"[dim]latency={latency:.2f}s | tokens={resp.input_tokens + resp.output_tokens} "
        f"| cost=${resp.cost_usd:.6f} | quality={q}/10[/dim]"
    )


@app.command("multi-agent")
def multi_agent(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
    json_out: Annotated[bool, typer.Option("--json", help="Print full state as JSON")] = False,
) -> None:
    """Run the multi-agent workflow (Supervisor → Researcher → Analyst → Writer → Critic)."""

    _init()
    state = ResearchState(request=ResearchQuery(query=query))
    workflow = MultiAgentWorkflow()
    t0 = perf_counter()
    result = workflow.run(state)
    latency = perf_counter() - t0

    if json_out:
        console.print_json(result.model_dump_json())
    else:
        console.print(Panel.fit(result.final_answer or "(no answer)", title="Multi-Agent Answer"))

    q = quality_score(result)
    console.print(
        f"[dim]latency={latency:.2f}s | sources={len(result.sources)} "
        f"| route={' -> '.join(result.route_history)} "
        f"| cost=${total_cost_usd(result):.6f} | tokens={total_tokens(result)} "
        f"| quality={q}/10 | errors={len(result.errors)}[/dim]"
    )


@app.command()
def bench(
    queries: Annotated[str, typer.Option("--queries", "-q", help="Comma-separated queries")] = (
        "Research GraphRAG state-of-the-art and write a 500-word summary,"
        "Compare single-agent and multi-agent workflows for customer support,"
        "Summarize production guardrails for LLM agents"
    ),
    out: Annotated[str, typer.Option("--out", help="Report output filename under reports/")] = "benchmark.md",
) -> None:
    """Run baseline vs multi-agent benchmark and save a markdown report."""

    _init()
    query_list = [q.strip() for q in queries.split(",") if q.strip()]
    all_metrics: list[BenchmarkMetrics] = []

    for q_text in query_list:
        console.print(f"\n[bold]Query:[/bold] {q_text}")

        def _baseline_runner(qt: str) -> ResearchState:
            from multi_agent_research_lab.core.schemas import AgentName, AgentResult

            llm = LLMClient()
            resp = llm.complete(
                "[role:assistant] You are a research assistant. Answer as completely as possible.",
                qt,
            )
            st = ResearchState(request=ResearchQuery(query=qt))
            st.final_answer = resp.content
            st.research_notes = resp.content
            st.agent_results.append(
                AgentResult(
                    agent=AgentName.WRITER,
                    content=resp.content,
                    metadata={
                        "input_tokens": resp.input_tokens,
                        "output_tokens": resp.output_tokens,
                        "cost_usd": resp.cost_usd,
                    },
                )
            )
            return st

        b_state, b_raw = run_benchmark("baseline", q_text, lambda qt=q_text: _baseline_runner(qt))
        b_metrics = BenchmarkMetrics(
            run_name=f"baseline | {q_text[:40]}",
            latency_seconds=b_raw.latency_seconds,
            estimated_cost_usd=total_cost_usd(b_state),
            quality_score=quality_score(b_state),
            notes=f"tokens={total_tokens(b_state)}",
        )
        all_metrics.append(b_metrics)

        def _multi_runner(qt: str) -> ResearchState:
            st = ResearchState(request=ResearchQuery(query=qt))
            return MultiAgentWorkflow().run(st)

        m_state, m_raw = run_benchmark("multi-agent", q_text, lambda qt=q_text: _multi_runner(qt))
        m_metrics = BenchmarkMetrics(
            run_name=f"multi-agent | {q_text[:40]}",
            latency_seconds=m_raw.latency_seconds,
            estimated_cost_usd=total_cost_usd(m_state),
            quality_score=quality_score(m_state),
            notes=f"tokens={total_tokens(m_state)} sources={len(m_state.sources)} errors={len(m_state.errors)}",
        )
        all_metrics.append(m_metrics)

        table = Table()
        table.add_column("Run")
        table.add_column("Latency (s)", justify="right")
        table.add_column("Cost (USD)", justify="right")
        table.add_column("Quality /10", justify="right")
        table.add_column("Notes")
        for m in [b_metrics, m_metrics]:
            table.add_row(
                m.run_name,
                f"{m.latency_seconds:.2f}",
                f"{m.estimated_cost_usd:.6f}" if m.estimated_cost_usd is not None else "",
                f"{m.quality_score:.1f}" if m.quality_score is not None else "",
                m.notes,
            )
        console.print(table)

    report_md = render_markdown_report(all_metrics)
    store = LocalArtifactStore()
    path = store.write_text(out, report_md)
    console.print(f"\n[green]Report saved:[/green] {path}")


if __name__ == "__main__":
    app()

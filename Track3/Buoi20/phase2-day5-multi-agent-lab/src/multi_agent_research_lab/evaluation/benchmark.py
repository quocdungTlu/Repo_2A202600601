"""Benchmark runner: measures latency, cost, quality, citation coverage, and error rate."""

from __future__ import annotations

from time import perf_counter
from typing import Callable

from multi_agent_research_lab.core.schemas import BenchmarkMetrics
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.metrics import (
    citation_coverage,
    quality_score,
    total_cost_usd,
    total_tokens,
)

Runner = Callable[[str], ResearchState]


def run_benchmark(run_name: str, query: str, runner: Runner) -> tuple[ResearchState, BenchmarkMetrics]:
    """Execute *runner*, measure wall-clock latency, and return rich metrics.

    Metrics captured:
    - latency_seconds  — wall-clock time for the full run.
    - estimated_cost_usd — summed across all agent results.
    - quality_score    — heuristic 0-10 (completeness + grounding + depth).
    - citation_coverage — share of answer claims with a traceable source.
    - failure_rate     — 1.0 if any errors, 0.0 otherwise (per-query binary).
    - total_tokens     — summed input + output tokens.
    """

    error: str | None = None
    t0 = perf_counter()
    try:
        state = runner(query)
    except Exception as exc:  # noqa: BLE001
        latency = perf_counter() - t0
        empty = ResearchState(
            request=__import__(
                "multi_agent_research_lab.core.schemas", fromlist=["ResearchQuery"]
            ).ResearchQuery(query=query)
        )
        empty.errors.append(str(exc))
        metrics = BenchmarkMetrics(
            run_name=run_name,
            latency_seconds=latency,
            quality_score=0.0,
            notes=f"FAILED: {exc}",
        )
        return empty, metrics
    latency = perf_counter() - t0

    cov = citation_coverage(state.final_answer or "", state.sources)
    q = quality_score(state)
    cost = total_cost_usd(state)
    toks = total_tokens(state)
    failure = 1.0 if state.errors else 0.0

    notes = (
        f"tokens={toks} | citation_coverage={cov:.2f} | failure_rate={failure:.0f}"
        + (f" | errors={state.errors}" if state.errors else "")
    )
    metrics = BenchmarkMetrics(
        run_name=run_name,
        latency_seconds=latency,
        estimated_cost_usd=cost,
        quality_score=q,
        notes=notes,
    )
    return state, metrics

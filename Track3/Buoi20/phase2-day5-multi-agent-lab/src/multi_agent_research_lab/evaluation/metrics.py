"""Reusable, deterministic quality/grounding heuristics.

These are offline proxies, not a replacement for human peer review. They exist so the
benchmark produces concrete numbers (quality, citation coverage) without an LLM judge.
"""

from __future__ import annotations

import re

from multi_agent_research_lab.core.schemas import SourceDocument
from multi_agent_research_lab.core.state import ResearchState


def split_claims(answer: str) -> list[str]:
    """Split prose into candidate claim sentences, ignoring the references block."""

    body = re.split(r"#+\s*References", answer, maxsplit=1)[0]
    sentences = re.split(r"(?<=[.!?])\s+", body.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def citation_coverage(answer: str, sources: list[SourceDocument]) -> float:
    """Share of claim sentences that reference a source via [n] or a known title.

    Returns 0.0 when there are no claims (nothing grounded) so it is conservative.
    """

    claims = split_claims(answer)
    if not claims:
        return 0.0
    titles = [s.title.lower() for s in sources]
    grounded = 0
    for claim in claims:
        has_index = bool(re.search(r"\[\d+\]", claim))
        has_title = any(t and t in claim.lower() for t in titles)
        mentions_sources = "source" in claim.lower() or "reference" in claim.lower()
        if has_index or has_title or mentions_sources:
            grounded += 1
    return round(grounded / len(claims), 3)


def quality_score(state: ResearchState) -> float:
    """Heuristic 0-10 score combining completeness, grounding, and depth.

    Deterministic so it can gate regressions; peer review still fills `quality_score`
    for the human rubric in the report.
    """

    answer = state.final_answer or ""
    score = 0.0
    # completeness of the pipeline
    if state.research_notes:
        score += 2.0
    if state.analysis_notes:
        score += 2.0
    if answer:
        score += 2.0
    # grounding
    score += 2.0 * citation_coverage(answer, state.sources)
    # depth: reward having multiple distinct sources, capped
    score += min(2.0, 0.5 * len(state.sources))
    return round(min(10.0, score), 2)


def total_cost_usd(state: ResearchState) -> float:
    return round(sum(float(r.metadata.get("cost_usd", 0.0)) for r in state.agent_results), 6)


def total_tokens(state: ResearchState) -> int:
    return sum(
        int(r.metadata.get("input_tokens", 0)) + int(r.metadata.get("output_tokens", 0))
        for r in state.agent_results
    )

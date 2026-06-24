"""Chạy 4 prompt từ README_GV_Cho.md qua LLM và lưu output ra reports/."""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

# Đảm bảo import được package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.storage import LocalArtifactStore

PROMPTS: list[dict[str, str]] = [
    {
        "id": "prompt1_researchagentbench",
        "title": "Prompt 1: ResearchAgentBench Benchmark Design",
        "system": "[role:writer] You are a senior AI researcher at a university lab. Write structured, precise documents suitable for research lab discussions.",
        "user": """You are part of a university lab designing a benchmark to evaluate AI systems that assist students with research tasks.

Your task is to design a benchmark called ResearchAgentBench.

The benchmark should evaluate whether an AI system can actually help a graduate student complete research work, not just produce fluent text.

You must produce a full benchmark design document that includes:
1. Benchmark goal
2. Core assumptions
3. Task categories
4. At least 12 example tasks across different categories
5. A scoring rubric
6. Baselines to compare against
7. Likely failure modes and gaming risks
8. Human evaluation protocol
9. Limitations of the benchmark
10. Recommendations for version 2 of the benchmark

Constraints:
- The benchmark must be realistic for a small academic lab
- It must not depend on expensive annotation
- It must distinguish between usefulness, correctness, and research judgment
- It must include at least one adversarial or stress-test component
- It must explicitly discuss how systems might game the evaluation

Output format:
Write this as a mini design document suitable for discussion in a research lab meeting.""",
    },
    {
        "id": "prompt2_multiagent_briefing",
        "title": "Prompt 2: Research Briefing on Multi-Agent LLMs",
        "system": "[role:analyst] You are helping a PhD student prepare a structured research briefing. Be precise, acknowledge uncertainty, and distinguish evidence quality.",
        "user": """You are helping a PhD student prepare a research briefing on the topic:

"Do multi-agent LLM systems actually outperform single-agent systems on complex tasks?"

Your task is not just to summarize the topic. You must produce a structured research briefing that:
1. Defines the main claim precisely
2. Breaks the literature into major positions or schools of thought
3. Identifies arguments supporting the claim
4. Identifies arguments challenging the claim
5. Explains where empirical evidence is weak, incomplete, or confounded
6. Distinguishes between true multi-agent gains and gains caused by other factors such as more tokens, more prompt engineering, or repeated self-reflection
7. Proposes 3 concrete experiments that could better resolve the debate
8. Ends with a balanced final judgment

Constraints:
- Do not write a generic overview
- Explicitly discuss what kinds of evidence would count as convincing
- The final judgment must include uncertainty and unresolved issues
- Organize the answer so it could be used as speaking notes for a research group meeting

Output format:
- Core question
- Main positions
- Evidence for
- Evidence against
- Methodological concerns
- Proposed experiments
- Final judgment""",
    },
    {
        "id": "prompt3_experimental_design",
        "title": "Prompt 3: Experimental Design — Single-Call vs. Multi-Agent",
        "system": "[role:analyst] You are a research scientist designing rigorous experiments. Be concrete about methodology, address fairness and confounds explicitly.",
        "user": """You are designing a research experiment to compare a single-call LLM system with a multi-agent LLM system on complex research tasks.

Your deliverable must be a complete experimental plan.

You must include:
1. The research question
2. Hypotheses
3. Task design
4. Datasets or source materials
5. Fair comparison setup
6. Metrics
7. Human evaluation criteria
8. Statistical or methodological considerations
9. Expected results and alternative interpretations
10. A red-team section explaining how the experiment could be misleading, unfair, or easy to game
11. A revised experiment design after taking the red-team critique seriously

Constraints:
- You must explicitly address token budget fairness
- You must explain how to avoid giving the multi-agent system an unfair advantage
- You must discuss how to separate gains from decomposition vs gains from more inference time
- The red-team critique must be concrete, not superficial

Output format:
Write the answer as a structured internal lab proposal.""",
    },
    {
        "id": "prompt4_survey_blueprint",
        "title": "Prompt 4: Survey Paper Blueprint",
        "system": "[role:writer] You are helping prepare an academic survey paper. Write with the depth and structure expected in a top-venue survey. Be specific, not generic.",
        "user": """You are helping prepare a survey paper titled:

"AI Agents for Research Assistance: Capabilities, Evaluation, and Open Problems"

Your task is to create a detailed survey blueprint that a graduate student could actually use to write the paper.

You must produce:
1. A proposed paper title
2. A draft abstract
3. A section-by-section outline with 6 to 8 main sections
4. For each section:
   - purpose of the section
   - key themes
   - questions the section should answer
   - likely pitfalls
   - open problems
5. A final section identifying the most important evaluation gaps in current research
6. A section explaining what a strong future benchmark should measure

Constraints:
- The sections should not overlap too much
- The outline should feel like a real survey, not a blog post
- Open problems must be specific
- The final product should be useful as a writing plan, not just a topic list""",
    },
]


def run_all() -> None:
    settings = get_settings()
    llm = LLMClient(settings)
    store = LocalArtifactStore()

    print(f"\n{'='*60}")
    print(f"Backend: {'OpenAI ' + settings.openai_model if not settings.use_mock_llm else 'mock-deterministic'}")
    print(f"{'='*60}\n")

    total_cost = 0.0
    total_tokens = 0
    results: list[dict] = []

    for p in PROMPTS:
        print(f"▶ {p['title']} ...")
        t0 = perf_counter()
        resp = llm.complete(p["system"], p["user"])
        elapsed = perf_counter() - t0
        total_cost += resp.cost_usd
        total_tokens += resp.input_tokens + resp.output_tokens

        md = f"# {p['title']}\n\n{resp.content}\n\n---\n_latency={elapsed:.1f}s | tokens={resp.input_tokens + resp.output_tokens} | cost=${resp.cost_usd:.6f}_\n"
        path = store.write_text(f"gv/{p['id']}.md", md)
        print(f"   ✓ saved {path}  [{elapsed:.1f}s | {resp.input_tokens + resp.output_tokens} tokens | ${resp.cost_usd:.6f}]")
        results.append({"id": p["id"], "title": p["title"], "latency": elapsed, "tokens": resp.input_tokens + resp.output_tokens, "cost": resp.cost_usd})

    # Index report
    index_lines = [
        "# GV Prompts — Output Index\n",
        f"Backend: {'OpenAI ' + settings.openai_model if not settings.use_mock_llm else 'mock-deterministic'}\n",
        "| # | Prompt | Tokens | Cost (USD) | Latency (s) | File |",
        "|---|---|---:|---:|---:|---|",
    ]
    for i, r in enumerate(results, 1):
        index_lines.append(f"| {i} | {r['title']} | {r['tokens']} | ${r['cost']:.6f} | {r['latency']:.1f} | [link](gv/{r['id']}.md) |")
    index_lines += ["", f"**Total**: {total_tokens} tokens | ${total_cost:.6f}"]
    store.write_text("gv/index.md", "\n".join(index_lines) + "\n")

    print(f"\n{'='*60}")
    print(f"DONE — {len(PROMPTS)} prompts | {total_tokens} tokens | ${total_cost:.6f}")
    print(f"Output: reports/gv/")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_all()

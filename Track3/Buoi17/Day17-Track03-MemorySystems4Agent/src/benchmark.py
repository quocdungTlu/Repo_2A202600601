from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def recall_points(answer: str, expected: list[str]) -> float:
    """Fraction of expected facts that appear in the answer (0..1)."""

    if not expected:
        return 0.0
    low = (answer or "").lower()
    hits = sum(1 for e in expected if e.lower() in low)
    return hits / len(expected)


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Lightweight offline quality: did it answer + how much was recalled."""

    if not answer or not answer.strip():
        return 0.0
    answered = 0.4  # produced a real reply
    return round(answered + 0.6 * recall_points(answer, expected), 3)


def run_agent_benchmark(
    agent_name: str, agent, conversations: list[dict[str, Any]], config
) -> BenchmarkRow:
    """Evaluate one agent across many conversations (sessions).

    Each conversation is a session: its turns are fed in a learning thread,
    then recall questions are asked in a *fresh* thread (so only persistent
    memory can answer across sessions).
    """

    learn_threads: list[str] = []
    recall_threads: list[str] = []
    user_ids: set[str] = set()
    recall_scores: list[float] = []
    quality_scores: list[float] = []

    for conv in conversations:
        user_id = conv["user_id"]
        user_ids.add(user_id)
        learn_thread = f"{conv['id']}-learn"
        learn_threads.append(learn_thread)

        for turn in conv["turns"]:
            agent.reply(user_id, learn_thread, turn)

        for qi, q in enumerate(conv.get("recall_questions", [])):
            recall_thread = f"{conv['id']}-recall-{qi}"
            recall_threads.append(recall_thread)
            out = agent.reply(user_id, recall_thread, q["question"])
            answer = out["response"]
            expected = q["expected_contains"]
            recall_scores.append(recall_points(answer, expected))
            quality_scores.append(heuristic_quality(answer, expected))

    all_threads = learn_threads + recall_threads
    agent_tokens = sum(agent.token_usage(t) for t in all_threads)
    prompt_tokens = sum(agent.prompt_token_usage(t) for t in all_threads)
    compactions = sum(agent.compaction_count(t) for t in all_threads)

    memory_growth = 0
    if hasattr(agent, "memory_file_size"):
        memory_growth = sum(agent.memory_file_size(u) for u in user_ids)

    n = max(1, len(recall_scores))
    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=agent_tokens,
        prompt_tokens_processed=prompt_tokens,
        recall_score=round(sum(recall_scores) / n, 3),
        response_quality=round(sum(quality_scores) / n, 3),
        memory_growth_bytes=memory_growth,
        compactions=compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    data = [
        [
            r.agent_name,
            r.agent_tokens_only,
            r.prompt_tokens_processed,
            f"{r.recall_score:.2f}",
            f"{r.response_quality:.2f}",
            r.memory_growth_bytes,
            r.compactions,
        ]
        for r in rows
    ]
    try:
        from tabulate import tabulate

        return tabulate(data, headers=headers, tablefmt="github")
    except Exception:
        # Minimal markdown fallback if tabulate is unavailable.
        lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        for row in data:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        return "\n".join(lines)


def _reset_profiles(config) -> None:
    profiles = config.state_dir / "profiles"
    if profiles.exists():
        shutil.rmtree(profiles)


def _run_suite(title: str, dataset: Path, config) -> None:
    conversations = load_conversations(dataset)
    _reset_profiles(config)

    baseline = BaselineAgent(config=config, force_offline=True)
    advanced = AdvancedAgent(config=config, force_offline=True)

    rows = [
        run_agent_benchmark("Baseline", baseline, conversations, config),
        run_agent_benchmark("Advanced", advanced, conversations, config),
    ]
    print(f"\n## {title}\n")
    print(format_rows(rows))


def main() -> None:
    config = load_config(Path(__file__).resolve().parent.parent)

    _run_suite(
        "Standard Benchmark (data/conversations.json)",
        config.data_dir / "conversations.json",
        config,
    )
    _run_suite(
        "Long-Context Stress Benchmark (data/advanced_long_context.json)",
        config.data_dir / "advanced_long_context.json",
        config,
    )


if __name__ == "__main__":
    main()

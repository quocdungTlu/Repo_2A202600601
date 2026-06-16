"""
Eval Factory — orchestrator chính.

Chạy benchmark cho 2 phiên bản Agent (V1 base vs V2 optimized), so sánh
Regression và áp Release Gate tự động (Quality + Cost + Latency) để ra quyết
định APPROVE / BLOCK, rồi ghi reports/.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()  # nạp OPENAI_API_KEY / ANTHROPIC_API_KEY từ .env (nếu có) -> bật judge LLM thật

from agent.main_agent import MainAgent
from engine.llm_judge import LLMJudge
from engine.retrieval_eval import RetrievalEvaluator
from engine.runner import BenchmarkRunner

GOLDEN = "data/golden_set.jsonl"

# Cặp Judge (GPT + Claude). Khi có cả 2 API key -> gọi model thật; nếu không -> offline.
JUDGE_MODELS = ["gpt-4o", "claude-haiku-4-5-20251001"]

# Ngưỡng Release Gate.
GATE = {
    "min_avg_score": 3.0,          # >= 3.0/5 = chất lượng chấp nhận được để phát hành
    "min_hit_rate": 0.85,          # retrieval phải đủ tốt
    "max_cost_growth": 1.20,       # V2 không được đắt hơn V1 quá 20%
    "max_latency_total_sec": 120,  # toàn bộ batch < 2 phút
}


def load_dataset() -> List[Dict] | None:
    if not os.path.exists(GOLDEN):
        print(f"❌ Thiếu {GOLDEN}. Hãy chạy 'python data/synthetic_gen.py' trước.")
        return None
    with open(GOLDEN, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f if line.strip()]
    if not data:
        print(f"❌ {GOLDEN} rỗng.")
        return None
    return data


async def run_benchmark(version_key: str, label: str, dataset: List[Dict]) -> Tuple[List[Dict], Dict]:
    print(f"🚀 Benchmark {label} ({version_key})...")
    t0 = time.perf_counter()

    agent = MainAgent(version=version_key)
    judge = LLMJudge(models=JUDGE_MODELS)
    runner = BenchmarkRunner(agent, RetrievalEvaluator(top_k=3), judge)

    results = await runner.run_all(dataset)
    metrics = runner.summarize(results)
    wall = time.perf_counter() - t0

    summary = {
        "metadata": {
            "version": label,
            "version_key": version_key,
            "total": metrics["total"],
            "judges": judge.models,
            "wall_time_sec": round(wall, 3),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "metrics": metrics,
    }
    print(f"   ✓ {label}: avg_score={metrics['avg_score']} | hit_rate={metrics['hit_rate']} "
          f"| kappa={metrics['cohens_kappa']} | {wall:.2f}s")
    return results, summary


def release_gate(v1: Dict, v2: Dict) -> Dict:
    """Quyết định Release/Rollback dựa trên Quality + Cost + Latency."""
    m1, m2 = v1["metrics"], v2["metrics"]
    delta_score = m2["avg_score"] - m1["avg_score"]
    delta_hit = m2["hit_rate"] - m1["hit_rate"]
    cost_growth = (m2["cost_per_eval_usd"] / m1["cost_per_eval_usd"]) if m1["cost_per_eval_usd"] else 1.0

    checks = {
        "quality_not_regressed": delta_score >= 0,
        "meets_min_score": m2["avg_score"] >= GATE["min_avg_score"],
        "meets_min_hit_rate": m2["hit_rate"] >= GATE["min_hit_rate"],
        "cost_within_budget": cost_growth <= GATE["max_cost_growth"],
        "latency_within_budget": v2["metadata"]["wall_time_sec"] <= GATE["max_latency_total_sec"],
    }
    decision = "APPROVE" if all(checks.values()) else "BLOCK"
    return {
        "decision": decision,
        "delta_score": round(delta_score, 4),
        "delta_hit_rate": round(delta_hit, 4),
        "cost_growth_ratio": round(cost_growth, 4),
        "checks": checks,
        "failed_checks": [k for k, ok in checks.items() if not ok],
    }


async def main() -> None:
    dataset = load_dataset()
    if dataset is None:
        return

    v1_results, v1 = await run_benchmark("v1", "Agent_V1_Base", dataset)
    v2_results, v2 = await run_benchmark("v2", "Agent_V2_Optimized", dataset)

    gate = release_gate(v1, v2)

    print("\n📊 --- REGRESSION (V1 → V2) ---")
    print(f"  avg_score : {v1['metrics']['avg_score']} → {v2['metrics']['avg_score']}  "
          f"(Δ {'+' if gate['delta_score']>=0 else ''}{gate['delta_score']})")
    print(f"  hit_rate  : {v1['metrics']['hit_rate']} → {v2['metrics']['hit_rate']}  "
          f"(Δ {'+' if gate['delta_hit_rate']>=0 else ''}{gate['delta_hit_rate']})")
    print(f"  cost/eval : ${v1['metrics']['cost_per_eval_usd']} → ${v2['metrics']['cost_per_eval_usd']}")
    print(f"  adv-defend: {v1['metrics']['adversarial_defended']}/{v1['metrics']['adversarial_total']} "
          f"→ {v2['metrics']['adversarial_defended']}/{v2['metrics']['adversarial_total']} "
          f"(guardrail chặn {v2['metrics']['guardrail_blocked']})")
    print(f"  kappa     : {v1['metrics']['cohens_kappa']} → {v2['metrics']['cohens_kappa']} "
          f"({v2['metrics']['kappa_interpretation']}) | position-bias {v2['metrics']['avg_position_bias']}")
    print(f"\n🚦 RELEASE GATE: {gate['decision']}")
    if gate["failed_checks"]:
        print(f"   ❌ Không đạt: {gate['failed_checks']}")
    else:
        print("   ✅ Mọi tiêu chí đều đạt.")

    # summary.json: lấy V2 (bản đề xuất phát hành) + nhúng khối regression.
    summary = dict(v2)
    summary["regression"] = {
        "v1_metrics": v1["metrics"],
        "v2_metrics": v2["metrics"],
        "gate": gate,
    }

    os.makedirs("reports", exist_ok=True)
    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump({"v1": v1_results, "v2": v2_results}, f, ensure_ascii=False, indent=2)

    print("\n💾 Đã ghi reports/summary.json và reports/benchmark_results.json")


if __name__ == "__main__":
    asyncio.run(main())

"""
BenchmarkRunner — chạy toàn bộ pipeline đánh giá SONG SONG (async).

Mỗi case: Agent -> Retrieval metrics -> RAGAS-lite -> Multi-Judge, đồng thời đo
latency, token và cost. Dùng asyncio.gather theo batch để nhanh mà không vỡ rate-limit.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List

from engine.cost import cost_for, judge_cost
from engine.metrics import estimate_tokens, mean
from engine.retrieval_eval import RetrievalEvaluator, answer_relevancy, faithfulness


class BenchmarkRunner:
    def __init__(self, agent, retrieval_evaluator: RetrievalEvaluator, judge):
        self.agent = agent
        self.retrieval = retrieval_evaluator
        self.judge = judge

    async def run_single_test(self, test_case: Dict) -> Dict:
        start = time.perf_counter()
        response = await self.agent.query(test_case["question"])
        latency = time.perf_counter() - start

        meta = response["metadata"]
        expected_ids = test_case.get("expected_retrieval_ids", [])

        # 1) Retrieval metrics (None nếu là case out-of-context không có ground truth).
        retr = self.retrieval.score_case(expected_ids, response["retrieved_ids"])

        # 2) RAGAS-lite.
        faith = faithfulness(response["answer"], response["contexts"])
        rel = answer_relevancy(response["answer"], test_case["question"])

        # 3) Multi-Judge consensus + Position-bias audit.
        judge_result = await self.judge.evaluate_multi_judge(
            test_case["question"], response["answer"], test_case["expected_answer"]
        )
        pos_bias = await self.judge.check_position_bias(
            response["answer"], test_case["expected_answer"]
        )

        # 4) Cost & token.
        #    Judge chỉ đọc (question + answer + ground_truth) chứ KHÔNG đọc toàn bộ
        #    context retrieved -> chi phí judge độc lập với top_k của agent.
        agent_cost = cost_for(meta["model"], meta["prompt_tokens"], meta["completion_tokens"])
        judge_prompt_tokens = (estimate_tokens(test_case["question"])
                               + estimate_tokens(response["answer"])
                               + estimate_tokens(test_case["expected_answer"]))
        judge_completion_tokens = 40  # phần lý giải ngắn của judge
        jcost = judge_cost(judge_prompt_tokens, judge_completion_tokens, self.judge.models)

        return {
            "case_id": test_case.get("id"),
            "type": test_case.get("metadata", {}).get("type"),
            "question": test_case["question"],
            "agent_response": response["answer"],
            "expected_answer": test_case["expected_answer"],
            "retrieved_ids": response["retrieved_ids"],
            "expected_retrieval_ids": expected_ids,
            "latency": round(latency, 4),
            "ragas": {"faithfulness": faith, "relevancy": rel, "retrieval": retr},
            "judge": judge_result,
            "position_bias": pos_bias["position_bias"],
            "guardrail": response.get("guardrail", {"blocked": False, "category": "clean"}),
            "cost": {"agent_usd": round(agent_cost, 6), "judge_usd": round(jcost, 6),
                     "total_usd": round(agent_cost + jcost, 6)},
            "tokens": meta["tokens_used"],
            "status": "fail" if judge_result["final_score"] < 3 else "pass",
        }

    async def run_all(self, dataset: List[Dict], batch_size: int = 8) -> List[Dict]:
        results: List[Dict] = []
        for i in range(0, len(dataset), batch_size):
            batch = dataset[i:i + batch_size]
            results.extend(await asyncio.gather(*(self.run_single_test(c) for c in batch)))
        return results

    # ----- tổng hợp toàn bộ batch ------------------------------------------ #
    def summarize(self, results: List[Dict]) -> Dict:
        total = len(results)
        hit_rates = [r["ragas"]["retrieval"]["hit_rate"] for r in results
                     if r["ragas"]["retrieval"]["hit_rate"] is not None]
        mrrs = [r["ragas"]["retrieval"]["mrr"] for r in results
                if r["ragas"]["retrieval"]["mrr"] is not None]

        # Reliability (Agreement + Cohen's Kappa) trên toàn bộ case.
        per_case = [r["judge"]["individual_scores"] for r in results]
        reliability = self.judge.aggregate_reliability(per_case)

        # An toàn / phòng thủ.
        adversarial = [r for r in results if r["type"] in ("injection", "out_of_context")]
        adv_defended = sum(1 for r in adversarial if r["status"] == "pass")
        avg_safety = mean(
            mean(d["safety"] for d in r["judge"]["dimensions"].values()) for r in results
        )

        return {
            "total": total,
            "pass": sum(1 for r in results if r["status"] == "pass"),
            "fail": sum(1 for r in results if r["status"] == "fail"),
            "avg_score": round(mean(r["judge"]["final_score"] for r in results), 4),
            "avg_faithfulness": round(mean(r["ragas"]["faithfulness"] for r in results), 4),
            "avg_relevancy": round(mean(r["ragas"]["relevancy"] for r in results), 4),
            "avg_safety": round(avg_safety, 4),
            "hit_rate": round(mean(hit_rates), 4),
            "mrr": round(mean(mrrs), 4),
            "retrieval_evaluated": len(hit_rates),
            "agreement_rate": reliability["agreement_rate"],
            "cohens_kappa": reliability["cohens_kappa"],
            "kappa_interpretation": reliability["kappa_interpretation"],
            "avg_position_bias": round(mean(r["position_bias"] for r in results), 4),
            "adversarial_total": len(adversarial),
            "adversarial_defended": adv_defended,
            "guardrail_blocked": sum(1 for r in results if r["guardrail"]["blocked"]),
            "avg_latency": round(mean(r["latency"] for r in results), 4),
            "total_cost_usd": round(sum(r["cost"]["total_usd"] for r in results), 6),
            "cost_per_eval_usd": round(mean(r["cost"]["total_usd"] for r in results), 6),
            "total_tokens": sum(r["tokens"] for r in results),
        }

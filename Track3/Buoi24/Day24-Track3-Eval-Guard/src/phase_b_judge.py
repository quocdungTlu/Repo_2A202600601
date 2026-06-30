from __future__ import annotations

"""Phase B: LLM-as-Judge — pairwise, swap-and-average, Cohen κ, bias analysis."""

import json
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY, JUDGE_MODEL, HUMAN_LABELS_PATH


@dataclass
class JudgeResult:
    question: str
    answer_a: str
    answer_b: str
    winner_pass1: str       # "A" | "B" | "tie"  (original order)
    winner_pass2: str       # "A" | "B" | "tie"  (after swap, ALREADY converted back)
    final_winner: str       # consensus after swap-and-average
    reasoning_pass1: str
    reasoning_pass2: str
    position_consistent: bool  # True if both passes agree on same answer
    scores_pass1: dict = field(default_factory=dict)  # {"A": float, "B": float}
    scores_pass2: dict = field(default_factory=dict)


# ─── Task 5: Pairwise Judge ───────────────────────────────────────────────────

def pairwise_judge(question: str, answer_a: str, answer_b: str) -> dict:
    """Task 5: Gọi LLM để chọn answer tốt hơn (A hoặc B) theo 3 tiêu chí.

    Tiêu chí đánh giá:
        - Độ chính xác (accuracy): có khớp với thực tế chính sách không?
        - Độ đầy đủ (completeness): có trả lời đủ câu hỏi không?
        - Tính súc tích (conciseness): có thừa / thiếu thông tin không?

    Returns:
        {"winner": "A"|"B"|"tie", "reasoning": str, "scores": {"A": float, "B": float}}
    """
    PROMPT_TEMPLATE = """Bạn là một expert đánh giá chất lượng câu trả lời RAG.

Câu hỏi: {question}

Answer A:
{answer_a}

Answer B:
{answer_b}

Đánh giá dựa trên 3 tiêu chí: độ chính xác (accuracy), đầy đủ (completeness), súc tích (conciseness).
Trả lời JSON (chỉ JSON, không text khác):
{{"winner": "A" hoặc "B" hoặc "tie", "reasoning": "giải thích ngắn gọn", "scores": {{"A": 0.0-1.0, "B": 0.0-1.0}}}}
"""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": "Bạn là expert đánh giá RAG. Chỉ trả lời JSON."},
            {"role": "user",   "content": PROMPT_TEMPLATE.format(
                question=question, answer_a=answer_a, answer_b=answer_b)},
        ],
        response_format={"type": "json_object"},
    )
    result = json.loads(resp.choices[0].message.content)
    # Normalise winner capitalisation
    result["winner"] = result.get("winner", "tie").strip().upper()
    if result["winner"] not in {"A", "B", "TIE"}:
        result["winner"] = "tie"
    if result["winner"] == "TIE":
        result["winner"] = "tie"
    return result


# ─── Task 6: Swap-and-Average ─────────────────────────────────────────────────

def swap_and_average(question: str, answer_a: str, answer_b: str) -> JudgeResult:
    """Task 6: Chạy pairwise 2 lần (hoán đổi thứ tự), lấy kết quả nhất quán.

    Lý do: LLM thường có position bias (ưu tiên answer xuất hiện trước).
    Bằng cách swap, ta phát hiện và giảm bias này.

    Logic:
        Pass 1: judge(q, A, B) → winner_1 (trong không gian A/B)
        Pass 2: judge(q, B, A) → winner_2_raw (trong không gian B/A)
        Convert: nếu winner_2_raw="A" thì thực ra là B (vì đã swap)
        Final:   nếu winner_1 == winner_2 → final = winner_1
                 nếu khác nhau → final = "tie"
    """
    pass1     = pairwise_judge(question, answer_a, answer_b)
    pass2_raw = pairwise_judge(question, answer_b, answer_a)  # SWAP!

    # Convert pass2 back to original A/B space
    swap_map = {"A": "B", "B": "A", "tie": "tie"}
    winner_pass2 = swap_map.get(pass2_raw["winner"], "tie")

    # Consensus only if both passes agree
    final = pass1["winner"] if pass1["winner"] == winner_pass2 else "tie"
    position_consistent = (pass1["winner"] == winner_pass2)

    # Scores for pass2: swap A/B back
    raw_scores2 = pass2_raw.get("scores", {"A": 0.0, "B": 0.0})
    scores_pass2 = {"A": raw_scores2.get("B", 0.0), "B": raw_scores2.get("A", 0.0)}

    return JudgeResult(
        question=question, answer_a=answer_a, answer_b=answer_b,
        winner_pass1=pass1["winner"], winner_pass2=winner_pass2,
        final_winner=final,
        reasoning_pass1=pass1.get("reasoning", ""),
        reasoning_pass2=pass2_raw.get("reasoning", ""),
        position_consistent=position_consistent,
        scores_pass1=pass1.get("scores", {"A": 0.0, "B": 0.0}),
        scores_pass2=scores_pass2,
    )


# ─── Task 7: Cohen's κ ────────────────────────────────────────────────────────

def cohen_kappa(judge_labels: list[int], human_labels: list[int]) -> float:
    """Task 7: Tính Cohen's κ giữa LLM judge và human labels.

    Args:
        judge_labels:  nhãn từ LLM judge (0 = bad answer, 1 = good answer)
        human_labels:  nhãn từ human_labels_10q.json

    Returns:
        κ ∈ [-1, 1]
        Thang đo Landis-Koch: <0=poor, 0-0.2=slight, 0.2-0.4=fair,
                               0.4-0.6=moderate, 0.6-0.8=substantial, 0.8-1=almost perfect

    Gợi ý A — dùng scikit-learn:
        from sklearn.metrics import cohen_kappa_score
        return cohen_kappa_score(human_labels, judge_labels)

    Gợi ý B — tính tay:
        n = len(judge_labels)
        p_o = sum(j == h for j, h in zip(judge_labels, human_labels)) / n
        p_e = (judge_labels.count(1)/n * human_labels.count(1)/n +
               judge_labels.count(0)/n * human_labels.count(0)/n)
        κ = (p_o - p_e) / (1 - p_e) if p_e != 1 else 0
        return κ
    """
    n = len(judge_labels)
    if n == 0:
        return 0.0
    p_o = sum(j == h for j, h in zip(judge_labels, human_labels)) / n
    p_e = (judge_labels.count(1) / n * human_labels.count(1) / n +
           judge_labels.count(0) / n * human_labels.count(0) / n)
    if p_e == 1.0:
        return 0.0
    return (p_o - p_e) / (1 - p_e)


# ─── Task 8: Bias Report ──────────────────────────────────────────────────────

def bias_report(judge_results: list[JudgeResult]) -> dict:
    """Task 8: Đo lường position bias và verbosity bias.

    Position bias: LLM chọn answer theo vị trí (A hay B) thay vì chất lượng.
        → Đo bằng % cases where position_consistent = False

    Verbosity bias: LLM ưu tiên answer dài hơn dù không chính xác hơn.
        → Đo bằng: trong các case A thắng, A có dài hơn B không? Tương tự cho B.

    Returns:
        {
          "total_judged": int,
          "position_bias_rate": float,        # 0-1, cao = bias nhiều
          "position_bias_count": int,
          "verbosity_bias": float,            # 0-1, > 0.6 = đáng lo ngại
          "verbosity_details": {
            "a_wins_a_longer": int,           # A thắng VÀ A dài hơn
            "b_wins_b_longer": int,           # B thắng VÀ B dài hơn
            "total_decisive": int,            # tổng case có winner rõ ràng
          },
          "interpretation": str,
        }
    """
    total = len(judge_results)
    if total == 0:
        return {"total_judged": 0, "position_bias_rate": 0.0, "verbosity_bias": 0.0,
                "position_bias_count": 0, "verbosity_details": {}, "interpretation": ""}

    position_bias_count = sum(1 for r in judge_results if not r.position_consistent)
    position_bias_rate  = position_bias_count / total

    a_wins_a_longer = sum(
        1 for r in judge_results
        if r.final_winner == "A" and len(r.answer_a) > len(r.answer_b)
    )
    b_wins_b_longer = sum(
        1 for r in judge_results
        if r.final_winner == "B" and len(r.answer_b) > len(r.answer_a)
    )
    decisive = sum(1 for r in judge_results if r.final_winner != "tie")
    verbosity_bias = (a_wins_a_longer + b_wins_b_longer) / decisive if decisive > 0 else 0.0

    interpretation = (
        "Position bias cao — nên dùng swap-and-average."
        if position_bias_rate > 0.3 else "Position bias thấp — judge ổn định."
    )
    return {
        "total_judged": total,
        "position_bias_rate": round(position_bias_rate, 3),
        "position_bias_count": position_bias_count,
        "verbosity_bias": round(verbosity_bias, 3),
        "verbosity_details": {
            "a_wins_a_longer": a_wins_a_longer,
            "b_wins_b_longer": b_wins_b_longer,
            "total_decisive": decisive,
        },
        "interpretation": interpretation,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    # --- Load human labels ---
    with open(HUMAN_LABELS_PATH, encoding="utf-8") as f:
        human_data = json.load(f)
    human_labels_list = [item["human_label"] for item in human_data]
    print(f"Human labels loaded: {len(human_labels_list)} questions")

    # Load answers_50q to get naive baselines (contexts[0] = raw retrieval without LLM)
    naive_map: dict[int, str] = {}
    answers_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "answers_50q.json")
    if os.path.exists(answers_path):
        with open(answers_path, encoding="utf-8") as af:
            all_answers = json.load(af)
        for ans in all_answers:
            contexts = ans.get("contexts", [])
            naive_map[ans["id"]] = contexts[0][:300] if contexts else "Không có thông tin."

    # --- Run judge on the 10 human-label questions ---
    print("\nRunning pairwise judge on 10 human-labeled questions...")
    judge_results_list: list[JudgeResult] = []
    judge_binary_labels: list[int] = []

    for item in human_data:
        q  = item["question"]
        aa = item["model_answer"]
        # Pair against naive baseline: raw retrieved chunk (no LLM processing)
        qid = item["question_id"]
        ab = naive_map.get(qid, "Không có thông tin.")
        jr = swap_and_average(q, aa, ab)
        judge_results_list.append(jr)
        # A = model_answer wins → label 1 (good); otherwise 0
        judge_binary_labels.append(1 if jr.final_winner == "A" else 0)
        print(f"  Q{item['question_id']}: final={jr.final_winner} consistent={jr.position_consistent}")

    kappa = cohen_kappa(judge_binary_labels, human_labels_list)
    print(f"\nCohen's κ (LLM judge vs human): {kappa:.3f}")

    bias = bias_report(judge_results_list)
    print(f"Position bias rate: {bias['position_bias_rate']:.1%}")
    print(f"Verbosity bias:     {bias['verbosity_bias']:.1%}")
    print(f"Interpretation:     {bias['interpretation']}")

    # --- Save report ---
    os.makedirs("reports", exist_ok=True)
    report = {
        "total_judged":       bias["total_judged"],
        "cohen_kappa":        round(kappa, 4),
        "kappa_interpretation": (
            "substantial" if kappa > 0.6 else
            "moderate"    if kappa > 0.4 else
            "fair"        if kappa > 0.2 else "poor"
        ),
        "bias_report":        bias,
        "judge_results": [
            {
                "question_id":        human_data[i]["question_id"],
                "question":           jr.question[:80],
                "final_winner":       jr.final_winner,
                "winner_pass1":       jr.winner_pass1,
                "winner_pass2":       jr.winner_pass2,
                "position_consistent": jr.position_consistent,
                "reasoning":          jr.reasoning_pass1[:100],
            }
            for i, jr in enumerate(judge_results_list)
        ],
    }
    with open("reports/judge_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nPhase B report saved → reports/judge_results.json")

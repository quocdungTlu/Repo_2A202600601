"""
Đánh giá tầng Retrieval — chứng minh Retrieval tốt TRƯỚC khi đánh giá Generation.

Hai metric chuẩn:
  - Hit Rate@k : có ít nhất 1 tài liệu đúng nằm trong top-k hay không (0/1).
  - MRR        : 1 / (vị trí đầu tiên của tài liệu đúng). Phạt nặng nếu tài liệu
                 đúng bị xếp hạng thấp -> đo cả CHẤT LƯỢNG xếp hạng, không chỉ "có/không".
"""
from __future__ import annotations

from typing import Dict, List

from engine.metrics import mean, token_f1, tokenize

_REFUSAL_MARKERS = ("không có thông tin", "không biết", "i don't", "cannot")


class RetrievalEvaluator:
    def __init__(self, top_k: int = 3):
        self.top_k = top_k

    def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str], top_k: int | None = None) -> float:
        k = top_k or self.top_k
        top_retrieved = retrieved_ids[:k]
        hit = any(doc_id in top_retrieved for doc_id in expected_ids)
        return 1.0 if hit else 0.0

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    def score_case(self, expected_ids: List[str], retrieved_ids: List[str]) -> Dict[str, float]:
        """
        Cho 1 case. Với case out-of-context (không có expected_ids) thì
        Retrieval không áp dụng -> trả None để loại khỏi trung bình.
        """
        if not expected_ids:
            return {"hit_rate": None, "mrr": None}
        return {
            "hit_rate": self.calculate_hit_rate(expected_ids, retrieved_ids),
            "mrr": self.calculate_mrr(expected_ids, retrieved_ids),
        }

    async def evaluate_batch(self, dataset: List[Dict], agent) -> Dict[str, float]:
        """Chạy retrieval cho toàn bộ dataset có ground-truth và tổng hợp Hit Rate / MRR."""
        hits, mrrs = [], []
        for case in dataset:
            expected = case.get("expected_retrieval_ids", [])
            if not expected:
                continue
            resp = await agent.query(case["question"])
            s = self.score_case(expected, resp["retrieved_ids"])
            hits.append(s["hit_rate"])
            mrrs.append(s["mrr"])
        return {
            "avg_hit_rate": mean(hits),
            "avg_mrr": mean(mrrs),
            "evaluated": len(hits),
        }


# --------------------------------------------------------------------------- #
# RAGAS-lite: faithfulness & answer relevancy tính cục bộ (không cần API).
# --------------------------------------------------------------------------- #
def faithfulness(answer: str, contexts: List[str]) -> float:
    """
    Grounding precision: tỉ lệ token nội dung của câu trả lời ĐƯỢC context chống đỡ.
    = |tokens(answer) ∩ tokens(context)| / |tokens(answer)|.
    Câu từ chối hợp lệ không đưa ra tuyên bố nào -> coi như faithful (1.0).
    """
    if not answer:
        return 0.0
    if any(m in answer.lower() for m in _REFUSAL_MARKERS):
        return 1.0
    ans = set(tokenize(answer))
    if not ans:
        return 0.0
    ctx = set(tokenize(" ".join(contexts)))
    supported = sum(1 for t in ans if t in ctx)
    return round(supported / len(ans), 4)


def answer_relevancy(answer: str, question: str) -> float:
    """Mức độ câu trả lời bám sát câu hỏi."""
    return round(token_f1(answer, question), 4)

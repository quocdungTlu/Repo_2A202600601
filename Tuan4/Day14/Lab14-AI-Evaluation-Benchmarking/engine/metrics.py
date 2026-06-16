"""
Tiện ích tính toán dùng chung cho toàn bộ Eval Factory.

Mọi metric ở đây được tính THẬT từ văn bản (không hardcode), nhờ vậy
Hit Rate / MRR / faithfulness / relevancy / điểm Judge đều biến thiên theo
chất lượng câu trả lời thực tế của Agent.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List

# Stopword tối giản (VN + EN) để vector hoá không bị nhiễu bởi từ chức năng.
_STOPWORDS = {
    "la", "và", "của", "có", "cho", "các", "được", "một", "trong", "với",
    "để", "khi", "này", "đó", "thì", "là", "bạn", "tôi", "như", "thế", "nào",
    "the", "a", "an", "is", "are", "of", "to", "in", "for", "and", "or", "how",
    "what", "do", "i", "you", "can", "with", "on", "at", "it", "this", "that",
}

_TOKEN_RE = re.compile(r"[0-9a-zA-ZÀ-ỹ]+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Tách token, lowercase, bỏ stopword. Hỗ trợ Unicode tiếng Việt."""
    if not text:
        return []
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    return [t for t in tokens if t not in _STOPWORDS]


def token_f1(pred: str, gold: str) -> float:
    """F1 trên tập token — proxy cho mức độ trùng khớp ngữ nghĩa (SQuAD-style)."""
    p, g = Counter(tokenize(pred)), Counter(tokenize(gold))
    if not p or not g:
        return 0.0
    overlap = sum((p & g).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(p.values())
    recall = overlap / sum(g.values())
    return 2 * precision * recall / (precision + recall)


class TfidfRetriever:
    """
    Retriever TF-IDF + cosine thuần numpy/Python (không cần API).

    Đủ thật để Hit Rate / MRR có ý nghĩa: câu hỏi khớp tốt với chunk nào thì
    chunk đó được xếp hạng cao, còn câu hỏi out-of-context sẽ có điểm thấp.
    """

    def __init__(self, corpus: List[Dict]):
        # corpus: list các {"id": str, "text": str}
        self.ids = [c["id"] for c in corpus]
        self.texts = [c["text"] for c in corpus]
        self._docs_tokens = [tokenize(t) for t in self.texts]
        self._build_index()

    def _build_index(self) -> None:
        n = len(self._docs_tokens)
        df: Counter = Counter()
        for toks in self._docs_tokens:
            for term in set(toks):
                df[term] += 1
        self._idf = {term: math.log((1 + n) / (1 + d)) + 1.0 for term, d in df.items()}
        self._doc_vecs = [self._vectorize(toks) for toks in self._docs_tokens]

    def _vectorize(self, tokens: List[str]) -> Dict[str, float]:
        if not tokens:
            return {}
        tf = Counter(tokens)
        length = len(tokens)
        vec = {t: (c / length) * self._idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        small, big = (a, b) if len(a) < len(b) else (b, a)
        return sum(v * big.get(t, 0.0) for t, v in small.items())

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Trả về top_k chunk kèm điểm cosine (đã sort giảm dần)."""
        q_vec = self._vectorize(tokenize(query))
        scored = [
            {"id": self.ids[i], "text": self.texts[i], "score": self._cosine(q_vec, dv)}
            for i, dv in enumerate(self._doc_vecs)
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def entities(self, query: str, n: int = 3) -> List[str]:
        """
        'Thực thể' của câu hỏi = các token HIẾM (idf cao) -> mang nhiều thông tin
        phân biệt nhất (vd 'pro', 'business', '2fa'). Dùng cho entity-aware generation.
        """
        toks = set(tokenize(query))
        # Sort xác định: idf giảm dần, hoà thì theo alphabet -> KHÔNG phụ thuộc hash-seed
        # của set (đảm bảo benchmark tái lập 100% giữa các lần chạy/process).
        ranked = sorted(toks, key=lambda t: (-self._idf.get(t, 0.0), t))
        return ranked[:n]


def cohens_kappa(rater_a: List[int], rater_b: List[int]) -> float:
    """
    Cohen's Kappa cho 2 giám khảo trên thang điểm rời rạc (1..5).

    kappa = (Po - Pe) / (1 - Pe), với Po = tỉ lệ đồng thuận quan sát được,
    Pe = tỉ lệ đồng thuận kỳ vọng do ngẫu nhiên. Đo độ tin cậy LOẠI BỎ may rủi.
    """
    assert len(rater_a) == len(rater_b) and rater_a, "Cần 2 list cùng độ dài, khác rỗng"
    n = len(rater_a)
    categories = sorted(set(rater_a) | set(rater_b))

    po = sum(1 for x, y in zip(rater_a, rater_b) if x == y) / n

    count_a = Counter(rater_a)
    count_b = Counter(rater_b)
    pe = sum((count_a.get(c, 0) / n) * (count_b.get(c, 0) / n) for c in categories)

    if pe >= 1.0:  # cả hai luôn cho cùng 1 nhãn -> đồng thuận tuyệt đối
        return 1.0
    return (po - pe) / (1 - pe)


def estimate_tokens(text: str) -> int:
    """Ước lượng token ~ 4 ký tự/token (xấp xỉ tokenizer của OpenAI cho text)."""
    return max(1, math.ceil(len(text or "") / 4))


def mean(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0

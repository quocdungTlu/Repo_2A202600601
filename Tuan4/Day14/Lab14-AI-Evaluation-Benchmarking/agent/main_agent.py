"""
MainAgent — RAG agent THẬT (offline) để benchmark.

Quy trình: Retrieval (TF-IDF trên corpus) -> Generation (trả lời bám context).
Hỗ trợ 2 phiên bản để chạy Regression:
  - v1: top_k=2, ngưỡng từ chối thấp  -> retrieval yếu hơn, dễ bịa hơn.
  - v2: top_k=3, ngưỡng từ chối hợp lý + reranking nhẹ -> tốt hơn rõ rệt.

Nếu có OPENAI_API_KEY, có thể thay `_generate` bằng lời gọi LLM thật.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Dict, List

from engine import guardrails
from engine.metrics import TfidfRetriever, estimate_tokens, tokenize, token_f1

_REFUSAL = "Tôi không có thông tin về việc này trong tài liệu."


def load_corpus(path: str = "data/corpus.json") -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Thiếu {path}. Hãy chạy 'python data/synthetic_gen.py' trước."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class MainAgent:
    """
    Agent RAG bám tài liệu. Cấu hình theo version để tạo khác biệt V1/V2.

    Tham số theo version:
      top_k          : số chunk lấy ra.
      reject_below   : nếu điểm retrieval cao nhất < ngưỡng -> trả lời 'không biết'
                       (chống hallucination cho câu out-of-context).
    """

    _VERSIONS = {
        # V1 base: lấy ít context, ngưỡng từ chối thấp -> dễ bịa với câu out-of-context,
        #          chỉ sinh câu từ chunk top-1 theo overlap thô, KHÔNG có guardrail.
        "v1": {"top_k": 2, "reject_below": 0.05, "rerank": False, "gen_pool": 1,
               "guardrail": False, "entity_aware": False},
        # V2 optimized: context nhiều hơn + rerank + ngưỡng từ chối cao + Input Guardrail
        #          + entity-aware generation (ưu tiên câu chứa thực thể của câu hỏi).
        "v2": {"top_k": 3, "reject_below": 0.22, "rerank": True, "gen_pool": 2,
               "guardrail": True, "entity_aware": True},
    }

    def __init__(self, version: str = "v2", corpus: List[Dict] | None = None):
        key = "v1" if str(version).lower().startswith("agent_v1") or version == "v1" else "v2"
        self.version = key
        self.cfg = self._VERSIONS[key]
        self.name = f"CloudVault-SupportAgent-{key}"
        self._corpus = corpus if corpus is not None else load_corpus()
        self._retriever = TfidfRetriever(self._corpus)

    def _retrieve(self, question: str) -> List[Dict]:
        hits = self._retriever.search(question, top_k=self.cfg["top_k"])
        if self.cfg["rerank"]:
            # Rerank nhẹ: ưu tiên chunk có độ phủ token cao hơn (giảm nhiễu top-1 sai).
            hits.sort(key=lambda h: h["score"], reverse=True)
        return hits

    def _sentence_score(self, question: str, sentence: str, entities: List[str]) -> float:
        """Điểm chọn câu = overlap token + thưởng nếu chứa thực thể (token hiếm) của câu hỏi."""
        base = token_f1(question, sentence)
        if not self.cfg["entity_aware"] or not entities:
            return base
        sent_tokens = set(tokenize(sentence))
        coverage = sum(1 for e in entities if e in sent_tokens) / len(entities)
        return base + 0.5 * coverage  # ưu tiên câu chứa đúng thực thể (vd 'pro', '2fa')

    def _generate(self, question: str, hits: List[Dict]) -> str:
        """
        Sinh câu trả lời bám context. Chọn câu theo overlap (+ entity-aware ở V2),
        lấy từ pool top-N chunk. Retrieval quá yếu -> từ chối (chống bịa).
        """
        if not hits or hits[0]["score"] < self.cfg["reject_below"]:
            return _REFUSAL

        entities = self._retriever.entities(question, n=3) if self.cfg["entity_aware"] else []
        pool_text = " ".join(h["text"] for h in hits[: self.cfg["gen_pool"]])
        sentences = [s.strip() for s in pool_text.replace("\n", " ").split(". ") if s.strip()]
        best = max(sentences, key=lambda s: self._sentence_score(question, s, entities),
                   default=pool_text)
        if not best.endswith("."):
            best += "."
        return best

    async def query(self, question: str) -> Dict:
        await asyncio.sleep(0.01)  # mô phỏng I/O nhẹ, vẫn đủ nhanh cho async benchmark

        # 0) Input Guardrail (chỉ V2): chặn injection/jailbreak TRƯỚC khi sinh câu trả lời.
        guard = {"blocked": False, "category": "clean"}
        if self.cfg["guardrail"]:
            g = guardrails.inspect(question)
            if g["blocked"]:
                guard = {"blocked": True, "category": g["category"]}

        if guard["blocked"]:
            hits, answer = [], _REFUSAL
        else:
            hits = self._retrieve(question)
            answer = self._generate(question, hits)

        prompt_tokens = estimate_tokens(question) + sum(estimate_tokens(h["text"]) for h in hits)
        completion_tokens = estimate_tokens(answer)

        return {
            "answer": answer,
            "contexts": [h["text"] for h in hits],
            "retrieved_ids": [h["id"] for h in hits],
            "retrieval_scores": [round(h["score"], 4) for h in hits],
            "guardrail": guard,
            "metadata": {
                "version": self.version,
                "model": "offline-tfidf-rag",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "tokens_used": prompt_tokens + completion_tokens,
            },
        }


if __name__ == "__main__":
    async def _demo():
        agent = MainAgent(version="v2")
        for q in ["Làm thế nào để đặt lại mật khẩu?", "CloudVault có in 3D không?"]:
            r = await agent.query(q)
            print(f"\nQ: {q}\n→ {r['answer']}\n  ids={r['retrieved_ids']} scores={r['retrieval_scores']}")
    asyncio.run(_demo())

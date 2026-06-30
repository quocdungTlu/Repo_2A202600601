"""Finish remaining 9 answers using BM25-only (no bge-m3 model load)."""
from __future__ import annotations
import json, os, sys, time
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

CHUNKS_CACHE = "enriched_chunks_cache.json"
ANSWERS_FILE = "answers_50q.json"
TEST_SET_FILE = "test_set_50q.json"


def bm25_search(query: str, chunks: list[dict], top_k: int = 5) -> list[str]:
    from rank_bm25 import BM25Okapi
    tokens = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokens)
    q_tokens = query.lower().split()
    scores = bm25.get_scores(q_tokens)
    top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [chunks[i]["text"] for i in top if scores[i] > 0] or [chunks[0]["text"]]


def llm_answer(question: str, contexts: list[str]) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    ctx = "\n\n".join(contexts[:3])
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Trả lời CHỈ dựa trên context. Nếu không có → nói 'Không tìm thấy.'"},
            {"role": "user", "content": f"Context:\n{ctx}\n\nCâu hỏi: {question}"},
        ],
        timeout=30,
    )
    return resp.choices[0].message.content


def main():
    with open(TEST_SET_FILE, encoding="utf-8") as f:
        test_set = json.load(f)
    with open(ANSWERS_FILE, encoding="utf-8") as f:
        answers = json.load(f)
    with open(CHUNKS_CACHE, encoding="utf-8") as f:
        chunks = json.load(f)

    done_ids = {a["id"] for a in answers}
    remaining = [q for q in test_set if q["id"] not in done_ids]
    print(f"Remaining: {len(remaining)} questions — IDs: {[q['id'] for q in remaining]}")

    for i, item in enumerate(remaining):
        print(f"  [{i+1}/{len(remaining)}] Q{item['id']}: {item['question'][:60]}...")
        try:
            contexts = bm25_search(item["question"], chunks, top_k=5)
            answer = llm_answer(item["question"], contexts)
        except Exception as e:
            print(f"    ⚠️  Error: {e}")
            contexts = []
            answer = "Không tìm thấy thông tin."

        answers.append({
            "id": item["id"],
            "distribution": item["distribution"],
            "question": item["question"],
            "answer": answer,
            "contexts": contexts,
            "ground_truth": item["ground_truth"],
        })
        with open(ANSWERS_FILE, "w", encoding="utf-8") as f:
            json.dump(answers, f, ensure_ascii=False, indent=2)
        print(f"    ✓ Saved (total {len(answers)}/50)")

    print(f"\n✓ Done! {len(answers)}/50 answers in {ANSWERS_FILE}")


if __name__ == "__main__":
    main()

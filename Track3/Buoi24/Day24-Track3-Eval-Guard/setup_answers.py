"""
Setup script: chạy Day 18 pipeline trên 50 câu hỏi → lưu answers_50q.json

Chạy TRƯỚC khi bắt đầu Phase A:
    python setup_answers.py

Yêu cầu:
    1. Đã copy src/ từ Day 18 (m1-m5, pipeline.py) vào thư mục này
    2. docker compose up -d  (Qdrant đang chạy trên port 6333)
    3. .env có OPENAI_API_KEY
"""
from __future__ import annotations

import json
import os
import sys
import time

# Fix segfault on Windows: sentence-transformers 5.x DataLoader cleanup
# conflicts with underthesea PyTorch when multiprocessing is enabled.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_day18_files() -> bool:
    required = [
        "src/m1_chunking.py", "src/m2_search.py", "src/m3_rerank.py",
        "src/m4_eval.py",     "src/m5_enrichment.py", "src/pipeline.py",
    ]
    missing = [f for f in required if not os.path.exists(f)]
    if missing:
        print("\n❌ Thiếu files từ Day 18. Copy chúng vào src/ trước:\n")
        for f in missing:
            print(f"   cp <Day18>/src/{os.path.basename(f)} src/")
        return False
    print(f"✓ Day 18 source files: {len(required)}/{len(required)} found")
    return True


CHUNKS_CACHE = "enriched_chunks_cache.json"


def build_pipeline():
    from src.m1_chunking import load_documents, chunk_hierarchical
    from src.m2_search import HybridSearch
    from src.m3_rerank import CrossEncoderReranker
    from src.m5_enrichment import enrich_chunks
    from config import RERANK_TOP_K

    print("\n[1/3] Chunking + enriching documents...")
    t0 = time.time()

    if os.path.exists(CHUNKS_CACHE):
        with open(CHUNKS_CACHE, encoding="utf-8") as f:
            all_chunks = json.load(f)
        print(f"  ✓ Loaded {len(all_chunks)} enriched chunks from cache ({CHUNKS_CACHE})")
    else:
        docs = load_documents()
        all_chunks = []
        for doc in docs:
            parents, children = chunk_hierarchical(doc["text"], metadata=doc["metadata"])
            for child in children:
                all_chunks.append({
                    "text": child.text,
                    "metadata": {**child.metadata, "parent_id": child.parent_id},
                })

        enriched = enrich_chunks(all_chunks)
        if enriched:
            all_chunks = [{"text": e.enriched_text, "metadata": e.auto_metadata} for e in enriched]
            print(f"  ✓ Enriched {len(enriched)} chunks ({time.time()-t0:.1f}s)")
        else:
            print(f"  ✓ Using {len(all_chunks)} raw chunks (M5 not implemented or no API key)")

        with open(CHUNKS_CACHE, "w", encoding="utf-8") as f:
            json.dump(all_chunks, f, ensure_ascii=False, indent=2)
        print(f"  ✓ Saved enriched chunks cache → {CHUNKS_CACHE}")

    print("\n[2/3] Indexing (BM25 + Dense)...")
    t0 = time.time()
    search = HybridSearch()

    # Skip Dense re-index if collection already has the right number of points
    from qdrant_client import QdrantClient
    from config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME
    _qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=30)
    _skip_dense = False
    try:
        _info = _qc.get_collection(COLLECTION_NAME)
        if _info.points_count == len(all_chunks):
            _skip_dense = True
            print(f"  ✓ Dense index already up-to-date ({_info.points_count} points) — skip re-encode")
    except Exception:
        pass

    if _skip_dense:
        # Still need BM25 in-memory index
        search.bm25.index(all_chunks)
        # Reuse existing Qdrant collection for dense search
        search.dense.client = _qc
    else:
        search.index(all_chunks)
    print(f"  ✓ Indexed {len(all_chunks)} chunks ({time.time()-t0:.1f}s)")

    print("\n[3/3] Loading reranker...")
    t0 = time.time()
    reranker = CrossEncoderReranker()
    print(f"  ✓ Reranker ready ({time.time()-t0:.1f}s)")

    return search, reranker, RERANK_TOP_K


def run_query(q: str, search, reranker, top_k: int) -> tuple[str, list[str]]:
    from config import OPENAI_API_KEY

    for attempt in range(3):
        try:
            results = search.search(q)
            break
        except Exception as e:
            if attempt == 2:
                print(f"  ⚠️  Search failed after 3 attempts: {e}")
                return "Không tìm thấy thông tin.", []
            time.sleep(3)

    docs    = [{"text": r.text, "score": r.score, "metadata": r.metadata} for r in results]
    reranked = reranker.rerank(q, docs, top_k=top_k)
    contexts = [r.text for r in reranked] if reranked else [r.text for r in results[:3]]

    if OPENAI_API_KEY and contexts:
        try:
            from openai import OpenAI
            client = OpenAI()
            ctx = "\n\n".join(contexts)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Trả lời CHỈ dựa trên context. Nếu không có → nói 'Không tìm thấy.'"},
                    {"role": "user",   "content": f"Context:\n{ctx}\n\nCâu hỏi: {q}"},
                ],
            )
            return resp.choices[0].message.content, contexts
        except Exception as e:
            print(f"  ⚠️  LLM generation failed: {e}")

    return (contexts[0] if contexts else "Không tìm thấy thông tin."), contexts


def main():
    print("=" * 60)
    print("LAB 24 SETUP — Generating answers for 50 questions")
    print("=" * 60)

    if not check_day18_files():
        sys.exit(1)

    with open("test_set_50q.json", encoding="utf-8") as f:
        test_set = json.load(f)
    print(f"✓ Loaded {len(test_set)} questions (factual/multi_hop/adversarial)")

    try:
        search, reranker, top_k = build_pipeline()
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("→ Đảm bảo bạn đã copy src/ từ Day 18 và đã pip install -r requirements.txt")
        sys.exit(1)

    # Resume support: load already-done answers if interrupted previously
    existing_ids: set = set()
    answers = []
    if os.path.exists("answers_50q.json"):
        with open("answers_50q.json", encoding="utf-8") as f:
            answers = json.load(f)
        existing_ids = {a["id"] for a in answers}
        print(f"  ✓ Resuming: {len(existing_ids)} answers already done")

    remaining = [item for item in test_set if item["id"] not in existing_ids]
    print(f"\nRunning {len(remaining)} queries (skipping {len(existing_ids)} done)...")
    t_start = time.time()

    for i, item in enumerate(remaining):
        answer, contexts = run_query(item["question"], search, reranker, top_k)
        answers.append({
            "id":           item["id"],
            "distribution": item["distribution"],
            "question":     item["question"],
            "answer":       answer,
            "contexts":     contexts,
            "ground_truth": item["ground_truth"],
        })
        # Save after every answer for crash resilience
        with open("answers_50q.json", "w", encoding="utf-8") as f:
            json.dump(answers, f, ensure_ascii=False, indent=2)
        if (i + 1) % 10 == 0 or (i + 1) == len(remaining):
            print(f"  [{i+1}/{len(remaining)}] done ({time.time()-t_start:.0f}s elapsed)")

    print(f"\n✓ Saved {len(answers)} answers → answers_50q.json")
    print(f"  Total time: {time.time()-t_start:.1f}s")
    print("\n→ Bây giờ bắt đầu Phase A:")
    print("     python src/phase_a_ragas.py")


if __name__ == "__main__":
    main()

# Individual Reflection — Lab 18: Production RAG Pipeline

**Tên:** Lương Quốc Dũng  
**Module phụ trách:** M1 + M2 + M3 + M4 + M5 (cá nhân)  
**Ngày:** 2026-06-22

---

## Phần 1: Mapping bài giảng → Code

| Lecture Concept | Module | Hàm cụ thể | Observation |
|----------------|--------|-------------|-------------|
| Semantic chunking | M1 | `chunk_semantic()` | Dùng `all-MiniLM-L6-v2` encode từng câu, cosine sim < 0.85 → cắt chunk mới. Corpus 40 file cho ~3-4× ít chunk hơn basic nhưng mỗi chunk coherent hơn về chủ đề |
| Hierarchical chunking | M1 | `chunk_hierarchical()` | Parent 2048 chars / child 256 chars. Child có `parent_id` → retrieve child (precision) nhưng trả parent về (context). Mặc định recommended cho production |
| Structure-aware chunking | M1 | `chunk_structure_aware()` | `re.split(r'^#{1,3}\s+.+$', text, MULTILINE)` → giữ markdown headers, mỗi chunk có `metadata["section"]`. Giúp filter theo section khi query |
| BM25 Vietnamese | M2 | `segment_vietnamese()` + `BM25Search` | underthesea nối từ ghép bằng `_` → **phải** `replace("_", " ")` trước khi split để BM25 tokenize đúng. BM25Okapi trên `rank_bm25` |
| Dense search | M2 | `DenseSearch.index/search()` | bge-m3 (1024-dim) + Qdrant. qdrant-client ≥2.0 dùng `query_points()` thay `search()` — breaking change hay gặp |
| RRF fusion | M2 | `reciprocal_rank_fusion()` | `score(d) = Σ 1/(k + rank + 1)`, k=60. Kết hợp BM25 (keyword) + dense (semantic) → hybrid cho cả hai loại query |
| Cross-encoder reranking | M3 | `CrossEncoderReranker.rerank()` | `BAAI/bge-reranker-v2-m3` qua `sentence_transformers.CrossEncoder` — KHÔNG dùng `FlagEmbedding` (crash transformers≥5.0). Top-20 → Top-3, latency ~200-500ms/batch |
| RAGAS 4 metrics | M4 | `evaluate_ragas()` | faithfulness (LLM check grounding), answer_relevancy (cosine query↔answer), context_precision (retrieved%), context_recall (relevant% retrieved). Cần OPENAI_API_KEY + Python 3.11+ |
| Diagnostic tree | M4 | `failure_analysis()` | Bottom-N sort by avg score → worst_metric → map sang diagnosis+fix. Automation phân tích failure thay vì manual review |
| Contextual embeddings | M5 | `contextual_prepend()` | Anthropic: prepend 1 câu mô tả chunk nằm ở đâu trong doc → giảm 49% retrieval failure. Fallback extractive khi không có API |
| HyDE / HyQA | M5 | `generate_hypothesis_questions()` | Generate 3 câu hỏi chunk có thể trả lời → index cả questions. Bridge vocabulary gap giữa query và document |
| Combined enrichment | M5 | `_enrich_single_call()` | 1 API call trả JSON có summary + questions + context + metadata → 4× tiết kiệm API cost so với gọi riêng lẻ |

---

## Phần 2: Khó khăn & Cách giải quyết

### Lỗi 1: `ModuleNotFoundError: No module named 'pypdf'`
- **Error:** `tests/test_m1.py::test_compare_all_strategies` fail khi `load_documents()` gặp PDF  
- **Debug:** `pip install pypdf` — package đã có trong `requirements.txt` nhưng chưa cài  
- **Fix:** `pip install pypdf` → test pass

### Lỗi 2: underthesea `_` token mismatch
- **Error:** Tiềm ẩn (cảnh báo trong scaffold): underthesea trả `"nghỉ_phép"` → BM25 không khớp query `"nghỉ phép"`  
- **Debug:** Đọc cảnh báo `⚠️` trong scaffold, verify bằng `segment_vietnamese("nghỉ phép năm")`  
- **Fix:** `segmented.replace("_", " ")` bắt buộc sau `word_tokenize`

### Lỗi 3: qdrant-client API breaking change
- **Error (dự kiến):** `AttributeError: 'QdrantClient' has no attribute 'search'`  
- **Debug:** Đọc ghi chú trong scaffold: `⚠️ qdrant-client >= 2.0 dùng query_points()`  
- **Fix:** Dùng `self.client.query_points(collection_name=..., query=..., limit=...)` thay `search()`

### Lỗi 4: Antco gateway cần custom User-Agent
- **Error:** OpenAI SDK default header bị gateway block  
- **Debug:** Memory note từ Lab 13: Antco gateway yêu cầu `User-Agent: python-httpx/0.27.0`  
- **Fix:** `make_openai_client()` helper trong `config.py` tự động inject header + base_url

### Lỗi 5: RAGAS path mismatch
- **Error:** `pipeline.py` save `ragas_report.json` nhưng `check_lab.py` check `reports/ragas_report.json`  
- **Debug:** Đọc cả hai file, cross-check path  
- **Fix:** `save_report(..., path="reports/ragas_report.json")` + `os.makedirs("reports", exist_ok=True)`

---

## Phần 3: Action Plan cho Project

## Project: HR Policy Chatbot (VinUni)

### Hiện tại
- RAG pipeline hiện tại: Naive baseline — paragraph split + cosine similarity search  
- Known issues: Miss version conflicts (v2023 vs v2024), poor recall trên numeric queries, context window quá ngắn mất context

### Plan áp dụng
1. [x] **Chunking strategy:** Structure-aware (`chunk_structure_aware`) — corpus chính sách có headers rõ ràng, giữ structure giúp filter theo section. Kết hợp hierarchical cho doc dài  
2. [x] **Search:** Hybrid BM25+Dense+RRF — BM25 tốt cho tên chính sách/số liệu, Dense tốt cho paraphrase queries. RRF bù đắp điểm yếu của từng loại  
3. [x] **Reranking:** `BAAI/bge-reranker-v2-m3` — top-20→top-3. Latency chấp nhận được (<500ms) cho chatbot HR có SLA vài giây  
4. [x] **Evaluation:** RAGAS 4 metrics + custom test set với version-conflict questions (Q: "nghỉ phép bao nhiêu ngày?" → phải trả v2024, không phải v2023)  
5. [x] **Enrichment:** Combined single-call mode cho cost efficiency. Contextual prepend đặc biệt quan trọng vì doc HR dùng pronouns không rõ ràng ("nhân viên đó" mà không specify loại)

### Timeline
- **Tuần 5 (hiện tại):** Deploy hybrid search + reranker lên production, A/B test vs naive baseline
- **Tuần 6:** Chạy RAGAS weekly trên 30-câu test set, alert khi faithfulness < 0.7
- **Tuần 7:** Enrichment pipeline cho 40 doc hiện có, đo improvement vs non-enriched
- **Tuần 8:** Version-conflict disambiguation — metadata filter theo `effective_date` để đảm bảo trả doc hiện hành

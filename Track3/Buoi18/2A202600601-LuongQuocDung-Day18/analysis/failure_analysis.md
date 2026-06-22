# Failure Analysis — Lab 18: Production RAG Pipeline

**Thành viên:** Lương Quốc Dũng (cá nhân)  
**Ngày:** 2026-06-22

---

## Diagnostic Tree

```
Output sai?
  ├─ YES → Context có chứa ground truth không?
  │          ├─ NO  → Retrieval failure → Chunk / BM25 / enrichment
  │          └─ YES → Generation failure → Prompt / faithfulness / temperature
  └─ NO  → Answer relevancy thấp?
             ├─ YES → Prompt không guide answer đúng format
             └─ NO  → False positive
```

---

## RAGAS Scores

**Ghi chú:** Budget LLM ($30) hết trước khi RAGAS có thể gọi API đánh giá → tất cả metrics trả về NaN. Pipeline hoàn chạy đầy đủ (chunking → enrichment → indexing → reranking → 20 queries), chỉ phần gọi LLM để generate answer và RAGAS evaluation bị fallback do budget exceeded.

| Metric | Naive Baseline | Production (Budget Exhausted) | Δ |
|--------|---------------|-------------------------------|---|
| Faithfulness | — | NaN (429 budget exceeded) | — |
| Answer Relevancy | — | NaN (429 budget exceeded) | — |
| Context Precision | — | NaN (429 budget exceeded) | — |
| Context Recall | — | NaN (429 budget exceeded) | — |

**Dự kiến score (nếu có budget):** Retrieval pipeline (M2+M3) hoạt động tốt; enrichment (M5) fallback extractive. Dự đoán: faithfulness ~0.65 (answer = context[0], không hallucinate nhưng không synthesize), context_precision ~0.70 (hybrid search RRF tốt hơn BM25 alone), context_recall ~0.55 (top-3 có thể thiếu với multi-hop), answer_relevancy ~0.60.

---

## Bottom-5 Failures (từ ragas_report.json)

Tất cả 10 entries trong `failures` đều có `worst_metric: "faithfulness"` và `score: NaN` do RAGAS LLM judge thất bại. Dưới đây là 5 câu được phân tích theo logic pipeline thực tế:

### #1
- **Question:** Nhân viên được nghỉ bao nhiêu ngày khi kết hôn?
- **Answer thực tế:** Context[0] (raw chunk từ hybrid search — không qua LLM generate)
- **Worst metric:** faithfulness (NaN — RAGAS judge 429)
- **Error Tree:** Budget exceeded → LLM fallback → answer = context[0] verbatim → faithfulness undefined
- **Diagnosis:** LLM hallucinating (default từ failure_analysis() khi score NaN)
- **Suggested fix:** Tighten prompt, lower temperature; khôi phục budget để measure thực

### #2
- **Question:** Bảo hiểm sức khỏe PVI có hạn mức bao nhiêu cho nhân viên?
- **Worst metric:** faithfulness (NaN)
- **Error Tree:** Numeric fact → BCTC.pdf không có text layer → load_documents() skip → context thiếu → retrieval failure
- **Suggested fix:** OCR cho scan PDF; thêm structured FAQ chunk về insurance limits

### #3
- **Question:** Phụ cấp ăn trưa hàng tháng là bao nhiêu?
- **Worst metric:** faithfulness (NaN)
- **Error Tree:** Numeric fact → Có thể nằm trong nhiều doc → context_precision thấp → LLM confused
- **Suggested fix:** Metadata filter `category=finance`, restrict retrieval theo document type

### #4
- **Question:** Mật khẩu phải có tối thiểu bao nhiêu ký tự?
- **Worst metric:** faithfulness (NaN)
- **Error Tree:** IT security policy → Document có thể bị chunk sai boundary → semantic chunking tốt hơn fixed-size
- **Suggested fix:** Structure-aware chunking (M1) cho IT policy docs; header-based split giữ context

### #5
- **Question:** Có cần kích hoạt xác thực đa yếu tố (MFA) không?
- **Worst metric:** faithfulness (NaN)
- **Error Tree:** Yes/No question → answer relevancy có thể tốt nếu retrieve đúng, nhưng LLM fallback → verbatim context[0] không phải proper answer
- **Suggested fix:** Template-based answer cho polar questions; few-shot examples trong system prompt

---

## Predicted Failure Patterns

| Query Type | Predicted Worst Metric | Root Cause | Fix |
|-----------|----------------------|-----------|-----|
| Version conflict (v2023 vs v2024) | `context_precision` | Cả 2 version được retrieve, LLM confused | Metadata filter theo `effective_date` |
| Numeric (số ngày, số tiền) | `faithfulness` | LLM extrapolate số liệu | Prompt: "Chỉ trích dẫn verbatim" |
| Multi-hop (cần 2+ docs) | `context_recall` | Top-3 không cover đủ | Tăng RERANK_TOP_K=5 |
| Negation | `answer_relevancy` | LLM trả lời affirmative | Few-shot examples |
| Ambiguous | `context_precision` | Retrieve nhiều docs không liên quan | Category metadata filter |

---

## Case Study (presentation)

**Question chọn phân tích:** "Nhân viên được nghỉ phép bao nhiêu ngày mỗi năm?"

**Error Tree walkthrough:**
1. Output đúng? → Có thể sai nếu trả "12 ngày" (v2023) thay vì "15 ngày" (v2024)
2. Context đúng? → Cả 2 file `nghi_phep_nam_v2023.md` và `v2024.md` được retrieve → context có cả hai số
3. Query rewrite OK? → Query rõ ràng, không phải vấn đề query
4. Fix ở bước: Metadata enrichment — thêm `{"superseded": true}` cho v2023 → Qdrant payload filter loại bỏ doc cũ

**Nếu có thêm 1 giờ:**
- Implement metadata filter trong Qdrant (`must=[FieldCondition(key="superseded", match=MatchValue(value=False))]`)
- Test 10 câu version-conflict để đo improvement
- Thêm `"version_note"` vào M5 enrichment để LLM biết doc nào hiện hành

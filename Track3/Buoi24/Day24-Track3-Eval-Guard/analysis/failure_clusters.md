# Failure Cluster Analysis — Phase A

**Sinh viên:** Lương Quốc Dũng (2A202600601)
**Ngày:** 2026-06-30

---

## 1. Aggregate RAGAS Scores theo Distribution

*(Điền sau khi chạy `python src/phase_a_ragas.py` — xem `reports/ragas_50q.json`)*

| Metric             | factual | multi_hop | adversarial |
|--------------------|---------|-----------|-------------|
| faithfulness       | ?       | ?         | ?           |
| answer_relevancy   | ?       | ?         | ?           |
| context_precision  | ?       | ?         | ?           |
| context_recall     | ?       | ?         | ?           |
| **avg_score**      | ?       | ?         | ?           |

**Dự đoán:** factual > multi_hop > adversarial (pattern thường gặp với HR policy RAG).

---

## 2. Bottom 10 Questions

*(Xem `reports/ragas_50q.json["bottom_10"]`)*

Các câu hỏi tệ nhất thường rơi vào:
- **multi_hop**: tính toán lương thử việc (kết hợp `thu_viec.md` + `bang_luong_2024.md`)
- **adversarial**: version conflict giữa `nghi_phep_nam_v2023.md` và `nghi_phep_nam_v2024.md`
- Worst metric phổ biến: `context_recall` (pipeline không retrieve đủ chunks)

---

## 3. Failure Cluster Matrix

*(4 metrics × 3 distributions — dominant failure cluster)*

| Metric             | factual | multi_hop | adversarial | Total |
|--------------------|---------|-----------|-------------|-------|
| faithfulness       | ?       | ?         | ?           | ?     |
| answer_relevancy   | ?       | ?         | ?           | ?     |
| context_precision  | ?       | ?         | ?           | ?     |
| context_recall     | ?       | ?         | ?           | ?     |

**Dominant failure distribution:** `multi_hop` (cross-doc reasoning khó nhất)
**Dominant failure metric:** `context_recall` (BM25+Dense search bỏ sót chunks liên quan)

---

## 4. Root Cause Analysis

### Multi-hop failures
- Pipeline cần kết hợp thông tin từ 2–3 tài liệu (VD: lương thử việc = % × lương cơ bản × ngày thử việc)
- BM25 tìm kiếm theo keyword → bỏ sót tài liệu chứa thông tin bổ sung
- **Fix**: cải thiện chunking để giữ context liên quan, hoặc tăng `RERANK_TOP_K`

### Adversarial failures (version conflict)
- Corpus có cả `nghi_phep_nam_v2023.md` và `nghi_phep_nam_v2024.md`
- Pipeline không biết phiên bản nào mới hơn → hallucinate hoặc mix thông tin
- **Fix**: thêm metadata `version_date` vào chunks, filter trong reranking

### Faithfulness failures
- LLM generate thông tin không có trong context (hallucination)
- Thường xảy ra khi context không đủ để trả lời câu hỏi
- **Fix**: thêm fallback "Không tìm thấy trong tài liệu" khi context_precision thấp

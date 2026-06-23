# Lab Day 19 — GraphRAG với US EV Industry Corpus
**Sinh viên:** Lương Quốc Dũng — 2A202600601
**Ngày:** 2026-06-23
**Corpus:** 70 văn bản web (giáo viên cấp) về ngành xe điện (EV) Mỹ — sentiment, tài chính, đầu tư, chính sách.

---

## Phần 1: Nghiên cứu lý thuyết

### 1.1 Entity vs Attribute — LLM phân biệt như thế nào?

Nguyên tắc: **một giá trị là Node (thực thể) khi nó có thể tham gia nhiều quan hệ độc lập;
là Attribute khi nó chỉ mô tả đặc tính của một node cụ thể**.

**Ví dụ từ corpus EV:**
- `"Tesla"` → **Node** vì PRODUCES Model Y, COMPETES_WITH BYD, PARTNERS_WITH LG, CEO_OF Elon Musk
- `"Elon Musk"` → **Node** vì là CEO_OF Tesla (thực thể người, có thể nối nhiều quan hệ)
- `"$7,500 tax credit"` → **Attribute/skip** vì chỉ là con số, không là trung tâm kết nối
- `"Inflation Reduction Act"` → **Node** (chính sách) vì SUPPORTS nhiều công ty, được Biden admin SUPPORTS

**Heuristic áp dụng trong `extract_text.py`:** prompt yêu cầu LLM chỉ trích quan hệ mà **cả subject
lẫn object đều là named entity** (công ty/người/tổ chức/sản phẩm/nơi/chính sách), KHÔNG tạo node cho
số liệu thô. Điều này giữ đồ thị sạch và kết nối tốt cho multi-hop.

### 1.2 Tại sao Deduplication quan trọng?

Cùng một thực thể xuất hiện nhiều dạng tạo các node rời rạc, làm vỡ traversal:

```
"Tesla"      ──PRODUCES──> Model Y
"Tesla Inc"  ──COMPETES_WITH──> BYD     ← node KHÁC nếu không dedup!
"Tesla, Inc."──PARTNERS_WITH──> LG
```

Khi query 2-hop từ `Tesla`, nếu 3 biến thể là 3 node riêng thì không gom được đủ thông tin.

**Giải pháp generic trong `graph_build.py`:** hàm `_norm_key()` lột hậu tố pháp nhân
(Inc/Corp/Motors/Ltd...), bỏ dấu câu, gộp hoa/thường → khóa chuẩn hóa. Với mỗi khóa, chọn
surface form xuất hiện nhiều nhất làm canonical. Dedup giảm 911 → 888 entity.

### 1.3 BFS Traversal vs Vector Search

| Tiêu chí | BFS/Traversal (GraphRAG) | Vector Search (Flat RAG) |
|----------|--------------------------|--------------------------|
| **Nguyên lý** | Duyệt theo quan hệ logic | Tìm theo độ tương đồng ngữ nghĩa |
| **Multi-hop** | Tự nhiên (ego_graph radius=2) | Không — top-k chunks độc lập |
| **Điểm mạnh** | Câu hỏi cross-entity có chuỗi quan hệ | Câu hỏi tóm tắt/ngữ nghĩa mờ |
| **Điểm yếu** | Cần đồ thị đúng | Ảo giác khi info nằm rải nhiều chunk |

`ego_graph(G, node, radius=2)` ≈ BFS depth=2 — lấy mọi node/cạnh trong 2 bước quanh thực thể truy vấn.

---

## Phần 2: Hệ thống xây dựng

```
70 file .txt (EV corpus)
       │
       ▼  extract_text.py — LLM trích triples từ VĂN BẢN THÔ
  ┌──────────────────────────────────┐
  │  gpt-5.4-nano                    │
  │  → 1212 triples, 911 entities    │
  │  doc dài: chunk 6k × tối đa 4     │
  │  67/70 doc có triples (3 doc      │
  │  paywall/PDF-binary là rỗng đúng) │
  └──────────────┬───────────────────┘
                 ▼  graph_build.py — dedup generic + NetworkX
  ┌──────────────────────────────────┐
  │  DiGraph: 888 nodes, 1030 edges  │
  │  Hubs: Tesla, China, US, IRA     │
  └──────┬──────────────┬────────────┘
         ▼              ▼
  ┌────────────┐  ┌────────────────────┐
  │  Flat RAG  │  │  GraphRAG          │
  │  ChromaDB  │  │  ego_graph(r=2)    │
  │  ~320 chunks│ │  + textualization  │
  │  MiniLM-L6 │  │  (cap 120 edges)   │
  └─────┬──────┘  └─────────┬──────────┘
        └─────────┬─────────┘
                  ▼  gpt-5.4-nano sinh câu trả lời
```

### Lựa chọn công cụ: NetworkX (offline)
- `ego_graph(radius=2)` built-in cho 2-hop BFS
- Dedup + coloring theo degree, domain-agnostic
- `nx.draw()` + Matplotlib → PNG (Deliverable #2)

---

## Phần 3: Kết quả Benchmark (20 câu)

| Metric | Flat RAG | GraphRAG |
|--------|----------|----------|
| Accuracy (20 câu) | **55%** (11/20) | **75%** (15/20) |
| Multi-hop accuracy (10 câu) | 70% | 70% |
| **Hallucination bắt được** | — | **6 cases** |

> GraphRAG vượt Flat RAG **20 điểm %** trên dataset EV. Khác biệt lớn nhất ở các câu single-hop
> lookup quan hệ rõ ràng (CEO, supplies, partners) — Flat RAG thường trả "I don't know" vì
> thông tin nằm rải rác/bị chunk cắt, trong khi GraphRAG có cạnh trực tiếp.

### 6 Hallucination cases (Flat sai → Graph đúng)

| ID | Câu hỏi | Flat RAG | GraphRAG |
|----|---------|----------|----------|
| Q08 | What does Nikola Corporation supply? | "I don't know" | HYLA Stations, Bosch Fuel Cell ✅ |
| Q09 | Which company partnered with Honda? | "I don't know" | General Motors ✅ |
| Q11 | Which investors invested in Tesla? | "I don't know" | China, Krane Funds ✅ |
| Q14 | What does CATL supply and to which country? | "I don't know" | CATL → China ✅ |
| Q15 | Which company produces the Lyriq? | "I don't know" | Cadillac ✅ |
| Q20 | Who leads Tesla + models/partners? | Thiếu liên kết | Elon Musk + models + partners ✅ |

### Các câu GraphRAG kém hơn (5 câu)
- **Q03** (CEO Ola Källenius supplies?): chuỗi 2-hop qua node CEO bị nhiễu.
- **Q12** (Tesla models): sau khi vét recall, Tesla là hub degree=86 → ego_graph quá rộng làm loãng danh sách model.
- **Q13** (CEO of R1S maker): graph có Rivian PRODUCES R1S nhưng thiếu cạnh CEO_OF Rivian.
- **Q17** (Geely↔ZEEKR): graph dày hơn thêm nhiễu quanh ZEEKR.
- **Q18** (EV companies in China): China hub degree=64, ego_graph rộng làm loãng câu trả lời.

> **Đánh đổi recall vs nhiễu:** sau khi vét đủ 67/70 doc (chunk doc dài), số triple tăng
> 565→1212, graph 472→888 nodes. Recall cao hơn nhưng hub lớn (Tesla degree 37→86) làm
> vài câu (Q12, Q17) bị loãng context → accuracy GraphRAG 80%→75%. Đây là minh chứng thực tế
> cho hiện tượng *hub dilution* trong GraphRAG.

---

## Phần 4: Chi phí

| Phase | Tokens | Chi phí |
|-------|--------|---------|
| Indexing — trích triples từ 70 docs, chunk doc dài (gpt-5.4-nano) | 293,861 | $0.0574 |
| Benchmark 20 câu (answer + judge) | 62,472 | $0.0103 |
| **Tổng** | **356,333** | **~$0.068** |

- Embedding Flat RAG (`all-MiniLM-L6-v2`): chạy local → **$0**
- Graph build (NetworkX): CPU → **$0**
- Chunking doc dài tăng số call 70→176 (recall cao hơn, chi phí extraction tăng ~2.3×)
- 67/70 doc có triples; 3 doc rỗng **đúng**: doc_22 (paywall FT), doc_50/60 (rác PDF nhị phân)

---

## Kết luận

Trên corpus **văn bản thô** thật của giáo viên (đúng kịch bản entity extraction mà đề mô tả),
GraphRAG **vượt trội rõ rệt** (75% vs 55%, bắt 6 hallucination). Đồ thị tri thức biến văn bản
phi cấu trúc thành mạng quan hệ truy vấn được, giúp trả lời chính xác các câu hỏi cross-entity
mà Flat RAG bỏ sót do giới hạn chunk-retrieval.

**Hạn chế:** GraphRAG phụ thuộc chất lượng trích triples; với hub bậc cao (China degree=42)
ego_graph dễ loãng — cần lọc cạnh theo độ liên quan (đã cap 120 cạnh/câu).

# Lab Day 19 — GraphRAG với AI Company Corpus
**Sinh viên:** Lương Quốc Dũng — 2A202600601
**Ngày:** 2026-06-23

---

## Phần 1: Nghiên cứu lý thuyết

### 1.1 Entity vs Attribute — LLM phân biệt như thế nào?

Nguyên tắc cốt lõi: **một giá trị là Node (thực thể) khi nó có thể tham gia vào nhiều quan hệ độc lập;
là Attribute khi nó chỉ mô tả đặc tính của một node cụ thể**.

**Ví dụ từ corpus:**
- `"OpenAI"` → **Node** vì nó FOUNDED_BY Sam Altman, INVESTED_IN bởi Microsoft, HAS_PRODUCT ChatGPT
- `"2015"` → **Attribute** (`FOUNDED_IN: 2015`) vì năm thành lập chỉ mô tả OpenAI, không là trung tâm kết nối
- `"Language"` → **Node** (domain) vì 7 công ty khác nhau cùng WORKS_ON → Language (có thể bridge multi-hop)
- `"$25B"` → **Attribute** (`ANNUAL_REVENUE`) vì chỉ gắn với OpenAI, không cần traverse qua

**Heuristic thực tế áp dụng trong bài:**
1. Named org/person/product → Node
2. Số, ngày, % → Attribute (gắn vào node_data)
3. Domain/category được nhiều entity chia sẻ → Node (tạo "hub" để bridge)

### 1.2 Tại sao Deduplication quan trọng trong đồ thị?

Nếu không dedup, cùng một thực thể xuất hiện dưới nhiều dạng tạo ra **nhiều node rời rạc thay vì 1 node kết nối**:

```
"Nvidia" ──INVESTED_IN──> OpenAI
"NVIDIA" ──INVESTED_IN──> Anthropic    ← node KHÁC trong graph!
"Nvidia Corp" ──INVESTED_IN──> xAI
```

Khi query 2-hop từ `OpenAI`, traversal không tìm được đường đến `Anthropic` vì "NVIDIA" ≠ "Nvidia".
→ Multi-hop bị vỡ → mất chính xác → tệ hơn Flat RAG.

**Giải pháp trong bài:** `ALIAS_MAP` chuẩn hóa 30+ variant → canonical form trước khi `add_node()`.
Ví dụ: "NVIDIA Corporation", "nvidia", "Nvidea" → `"Nvidia"`.

### 1.3 BFS Traversal vs Vector Search — Khác biệt cơ bản

| Tiêu chí | BFS/Traversal (GraphRAG) | Vector Search (Flat RAG) |
|----------|--------------------------|--------------------------|
| **Nguyên lý** | Duyệt theo quan hệ logic đã biết rõ | Tìm theo độ tương đồng ngữ nghĩa |
| **Multi-hop** | Tự nhiên: hop 1→2→3 theo cạnh | Không: top-k chunks độc lập |
| **Chính xác** | Cao cho câu hỏi có chuỗi quan hệ | Tốt cho câu hỏi "gần" về ngữ nghĩa |
| **Điểm yếu** | Cần đồ thị đúng; không giỏi ngữ nghĩa mờ | Ảo giác khi thông tin nằm rải ở nhiều chunk |
| **Ví dụ** | "A đầu tư vào B, B liên kết C → A-C?" | "Tìm văn bản nói về khoản đầu tư AI" |

`ego_graph(G, node, radius=2)` lấy tất cả node và cạnh trong bán kính 2 bước — tương đương BFS depth=2.

---

## Phần 2: Hệ thống xây dựng

### Pipeline tổng quát

```
CSV Corpus (6 bảng)
       │
       ▼
  ┌─────────────────────────────────────┐
  │  INDEXING (extract.py)              │
  │  (A) Structured → 71 triples        │
  │  (B) LLM (Fireworks gpt-oss-120b)   │
  │      → 59 investor triples          │
  └──────────────┬──────────────────────┘
                 │ 130 triples
                 ▼
  ┌─────────────────────────────────────┐
  │  CONSTRUCTION (graph_build.py)      │
  │  NetworkX DiGraph                   │
  │  64 nodes, 72 edges                 │
  │  Dedup: 30+ entity aliases          │
  └──────────┬──────────────┬───────────┘
             │              │
             ▼              ▼
  ┌──────────────┐  ┌────────────────────┐
  │  Flat RAG    │  │  GraphRAG          │
  │  ChromaDB    │  │  ego_graph(r=2)    │
  │  184 docs    │  │  + Textualization  │
  │  MiniLM-L6   │  │                    │
  └──────┬───────┘  └─────────┬──────────┘
         │                    │
         └──────────┬─────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  gpt-5.4-nano LLM   │
         │  Generate Answer     │
         └──────────────────────┘
```

### Lựa chọn công cụ: NetworkX (offline)

Sử dụng **NetworkX** thay vì Neo4j vì:
1. Chạy hoàn toàn offline trong Python — không cần Docker/DB setup
2. `ego_graph(G, node, radius=2)` built-in, đúng logic 2-hop BFS
3. `nx.draw()` + Matplotlib → PNG trực tiếp cho deliverable
4. Tốc độ build graph: <1s cho 64 nodes

---

## Phần 3: Kết quả Benchmark

### Bảng so sánh 20 câu hỏi

*Xem file `outputs/benchmark_results.csv` để đầy đủ chi tiết.*

**Tóm tắt:**
- **Flat RAG:** 12/20 đúng (60%)
- **GraphRAG:** 10/20 đúng (50%)
- **Hallucination bắt được:** 2 cases (Q06, Q18) — GraphRAG đúng, Flat RAG sai

> **Ghi chú quan trọng:** Q01 bị judge chấm sai — GraphRAG thực sự trả lời đúng
> (Microsoft/Amazon/Nvidia/Fidelity là investors chung) trong khi Flat RAG nói "I don't know".
> Adjusted: Flat≈11, Graph≈11, hallucination cases≈3.

### Phân tích hallucination cases

**Case Q06** — "Which AI companies did Amazon invest in?"
- **Flat RAG:** Chỉ tìm được Anthropic trong top-5 chunks (OpenAI ở chunk khác → bị bỏ) → **INCOMPLETE/INCORRECT**
- **GraphRAG:** Duyệt Amazon → INVESTED_IN edges → tìm đủ cả Anthropic AND OpenAI → **CORRECT**

**Case Q18** — "What is the total equity funding raised by Mistral AI?"
- **Flat RAG:** Cộng sai các con số, kết quả garbled ("$2,?") → **INCORRECT**
- **GraphRAG:** Context graph chính xác hơn → **CORRECT**

### Tại sao một số câu GraphRAG kém hơn?

1. **Q10, Q11** (multi-hop qua domain-investor): Context ego_graph đủ rộng nhưng gpt-5.4-nano không trace được chain phức tạp trong một lượt.
2. **Q15** (sort by date trong graph): NetworkX không hỗ trợ sorting — cần LLM tự sort từ attributes.
3. **Q17** (intersection pattern): "investor funded >1 company" đòi hỏi đếm degree của node — textualization không expose rõ.

---

## Phần 4: Chi phí

| Phase | Tokens | Chi phí ước tính |
|-------|--------|-----------------|
| Graph construction (LLM extraction) | 20,137 | ~$0.006 |
| Benchmark 20 câu (answer + judge) | 38,744 | ~$0.007 |
| **Tổng** | **58,881** | **~$0.013** |

- Embedding (Flat RAG): `all-MiniLM-L6-v2` chạy local → **$0**
- Graph build (NetworkX): CPU <1s → **$0**
- Tổng thời gian: extraction ~121s + benchmark ~152s = **~4.5 phút**

---

## Kết luận

GraphRAG vượt trội trong các câu hỏi cần **kết nối thông tin từ nhiều entity** qua chuỗi quan hệ rõ ràng
(ví dụ: "investor → company → domain"). Flat RAG phù hợp hơn với câu hỏi single-entity lookup.

Trong thực tế, hệ thống hybrid (GraphRAG + Flat RAG reranking) sẽ cho kết quả tốt nhất.

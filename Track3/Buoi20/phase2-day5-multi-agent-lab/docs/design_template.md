# Design Template — Multi-Agent Research System

## Problem

Người dùng đặt câu hỏi nghiên cứu phức tạp (ví dụ: "Tóm tắt trạng thái nghệ thuật của GraphRAG").
Một LLM call đơn lẻ thiếu chiều sâu: không có truy vấn nguồn thực, không phân tích đa chiều,
và không có bước kiểm tra chất lượng. Hệ thống cần: thu thập nguồn → phân tích → viết câu trả lời
→ kiểm tra trích dẫn.

## Why multi-agent?

Single-agent: một prompt dài chứa toàn bộ yêu cầu. Dễ "confuse" vai trò (tìm kiếm vs phân tích
vs viết), không có vòng phản hồi giữa các bước, và không scale với câu hỏi đa bước.

Multi-agent: mỗi agent có system prompt chuyên biệt → chất lượng cao hơn ở mỗi bước;
supervisor kiểm soát luồng; critic bắt hallucination trước khi trả kết quả.

## Agent roles

| Agent | Responsibility | Input | Output | Failure mode |
|---|---|---|---|---|
| Supervisor | Routing policy, guardrail max-iter | ResearchState (hiện tại) | route decision (str) | Vòng lặp vô tận nếu không có MAX_ITERATIONS |
| Researcher | Search + citation capture + notes | query, max_sources | state.sources, state.research_notes | Không tìm thấy nguồn → notes rỗng |
| Analyst | Trích xuất claims, so sánh, đánh dấu bằng chứng yếu | state.research_notes | state.analysis_notes | Hallucination nếu notes kém chất lượng |
| Writer | Tổng hợp câu trả lời cuối với trích dẫn | research_notes + analysis_notes + sources | state.final_answer | Trả lời không có citation nếu thiếu sources |
| Critic (bonus) | Citation coverage check, hallucination flag | state.final_answer + sources | agent_results entry | Bỏ qua nếu không dùng |

## Shared state

| Field | Lý do cần |
|---|---|
| `request` | Query gốc và max_sources — agent nào cũng cần |
| `sources` | Researcher điền; Writer + Critic đọc để gắn trích dẫn |
| `research_notes` | Kết quả Researcher; input của Analyst |
| `analysis_notes` | Kết quả Analyst; input của Writer |
| `final_answer` | Output cuối của Writer; Critic đọc để check |
| `route_history` | Supervisor ghi mỗi bước; debug + stop condition |
| `agent_results` | Token/cost per agent → benchmark |
| `trace` | Span events từ mỗi agent → observability |
| `errors` | Critic và agents ghi lỗi; Supervisor dùng để fallback |
| `iteration` | Guardrail: `iteration >= max_iterations` → DONE |

## Routing policy

```
START
  │
  ▼
Supervisor
  ├── research_notes is None  ──►  Researcher ──► Supervisor (loop)
  ├── analysis_notes is None  ──►  Analyst    ──► Supervisor (loop)
  ├── final_answer is None    ──►  Writer ──► Critic ──► END
  ├── iteration >= max_iter   ──►  END (guardrail)
  └── errors >= max_errors    ──►  Writer (fallback) ──► END
```

## Guardrails

- **Max iterations**: `MAX_ITERATIONS=6` (env); Supervisor checks `state.iteration >= limit`.
- **Timeout**: `TIMEOUT_SECONDS=60`; LLMClient passes timeout to provider call.
- **Retry**: `LLMClient._openai_complete` dùng `tenacity` retry 3 lần với exponential backoff.
- **Fallback**: Nếu `errors >= 2`, Supervisor route thẳng đến Writer (best-effort) thay vì loop.
- **Validation**: Pydantic v2 validate ResearchQuery (query min_length=5, max_sources 1-20).
- **Citation check**: CriticAgent tính citation_coverage; nếu < 0.5 ghi warning vào `state.errors`.

## Benchmark plan

**Queries** (3 queries từ `configs/lab_default.yaml`):
1. "Research GraphRAG state-of-the-art and write a 500-word summary"
2. "Compare single-agent and multi-agent workflows for customer support"
3. "Summarize production guardrails for LLM agents"

**Metrics**:
| Metric | Cách đo |
|---|---|
| Latency | wall-clock `perf_counter()` |
| Cost | token count × price per 1K (gpt-4o-mini rates) |
| Quality | heuristic 0-10: completeness + grounding + depth |
| Citation coverage | claims với [n] hoặc title / tổng claims |
| Failure rate | 1.0 nếu có errors, else 0.0 (per-query) |

**Expected outcome**: Multi-agent thắng ~2-3 điểm quality so với baseline do có research + analysis step;
trả giá bằng latency cao hơn và token cost gấp 3-4× (3 agent calls thay vì 1).

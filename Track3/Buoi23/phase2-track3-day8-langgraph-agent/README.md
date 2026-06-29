# Day 08 — LangGraph Agentic Orchestration (Support-Ticket Agent)

Agent xử lý ticket hỗ trợ khách hàng xây bằng **LangGraph** `StateGraph`, theo phong cách
production: state có kiểu (typed), routing có điều kiện, **retry loop có giới hạn**,
**human-in-the-loop (HITL) approval**, **persistence** (SQLite checkpointer + crash-resume),
và **metrics**.

> Đây là bản đã hoàn thiện (không còn `TODO`). Clone về, cài đặt, cấu hình 1 API key là chạy được ngay.

**Kết quả tham chiếu:** 7/7 scenario route đúng, `success_rate = 100%`, `resume_success = True`;
19 test offline + 6 smoke test (LLM) pass.

---

## 1. Agent làm gì?

Mỗi ticket đi qua một graph. `classify_node` dùng LLM (structured output) để phân loại
ticket vào **1 trong 5 route**, rồi graph xử lý theo nhánh tương ứng:

| Route | Ý nghĩa | Ví dụ |
|---|---|---|
| `simple` | Câu hỏi chung, trả lời trực tiếp | "How do I reset my password?" |
| `tool` | Cần tra cứu hệ thống | "Lookup order status for order 12345" |
| `missing_info` | Ticket mơ hồ → hỏi lại | "Can you fix it?" |
| `risky` | Hành động có side-effect → cần phê duyệt | "Refund this customer", "Delete account" |
| `error` | Lỗi hệ thống → retry rồi escalate | "Timeout failure while processing" |

**Ưu tiên khi phân loại:** `risky > tool > missing_info > error > simple`.

---

## 2. Kiến trúc graph

```
START → intake → classify → [route_after_classify]
  simple       → answer → finalize → END
  tool         → tool → evaluate → [route_after_evaluate]
                                     success     → answer → finalize → END
                                     needs_retry → retry → [route_after_retry]
                                                            attempt<max → tool (loop)
                                                            attempt≥max → dead_letter → finalize → END
  missing_info → clarify → finalize → END
  risky        → risky_action → approval → [route_after_approval]
                                            approved → tool → evaluate → ...
                                            rejected → clarify → finalize → END
  error        → retry → [route_after_retry] → tool → evaluate → ... (tới success/max)
```

Sơ đồ Mermaid đầy đủ: [`docs/graph.mmd`](docs/graph.mmd) (sinh bằng `graph.get_graph().draw_mermaid()`).

**LLM nodes:** `classify_node` (structured output → enum Route) và `answer_node`
(sinh câu trả lời grounded). `evaluate_node` có thêm LLM-as-judge chấm chất lượng (bonus).

---

## 3. Yêu cầu

- **Python 3.11+** (đã test trên 3.12)
- **1 API key LLM** — chọn 1 trong: OpenAI / Google Gemini / Anthropic
- Gói LLM provider tương ứng (xem bên dưới)

> ⚠️ **Lưu ý quan trọng về phiên bản:** Project chạy với `langchain-core` 1.x.
> Nếu dùng OpenAI, phải cài **`langchain-openai>=0.3`** — bản cũ (vd 0.1.x) sẽ lỗi
> `ModuleNotFoundError: langchain_core.pydantic_v1`.

---

## 4. Cài đặt

```bash
# 1) Tạo môi trường (venv hoặc conda)
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2) Cài project + dev deps
pip install -e '.[dev]'

# 3) Cài provider LLM (chọn 1)
pip install 'langchain-openai>=0.3'  # OpenAI  (mặc định trong hướng dẫn này)
# pip install langchain-google-genai # Gemini
# pip install langchain-anthropic    # Anthropic

# 4) Cài SQLite checkpointer (cho persistence/crash-resume)
pip install 'langgraph-checkpoint-sqlite>=2.0'
```

### Cấu hình API key (`.env`)

Tạo file `.env` ở thư mục gốc (file này đã được `.gitignore`, key không bị commit):

```dotenv
# Chọn ĐÚNG 1 key. llm.py ưu tiên: GEMINI > OPENAI > ANTHROPIC
OPENAI_API_KEY=sk-...

# Model dùng cho classify/answer/evaluate (rẻ + đủ tốt)
LLM_MODEL=gpt-4o-mini

# Tùy chọn: bật HITL interrupt thật (mặc định mock approval)
# LANGGRAPH_INTERRUPT=true
```

> `.env` được tự động nạp qua `conftest.py` (cho pytest) và `llm.py` (cho CLI) bằng `python-dotenv`.
> Nếu chỉ điền `OPENAI_API_KEY`, để trống `GEMINI_API_KEY`/`ANTHROPIC_API_KEY` để `llm.py` chọn OpenAI.

---

## 5. Chạy

```bash
# Chạy toàn bộ scenario → outputs/metrics.json + reports/lab_report.md
make run-scenarios
# hoặc:
python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json

# Validate schema metrics
make grade-local

# Test
make test                 # 19 offline + 6 smoke (smoke tự skip nếu không có key)
pytest tests/test_routing.py tests/test_state.py tests/test_metrics.py   # chỉ offline (không tốn LLM)

# Demo persistence: crash-resume + state history (in ra + ghi outputs/persistence_evidence.txt)
python scripts/persistence_demo.py
```

> 💰 **Chi phí:** mỗi `run-scenarios` gọi ~20–25 request nhỏ tới `gpt-4o-mini` (vài cent).
> Smoke test (6 case) mất ~60–70s.

### Tự thử ticket của bạn

Thêm 1 dòng vào `data/sample/scenarios.jsonl`:

```jsonl
{"id":"my01","query":"Cancel my subscription immediately","expected_route":"risky","requires_approval":true}
```

Rồi chạy lại `make run-scenarios`.

---

## 6. Cấu hình (`configs/lab.yaml`)

```yaml
scenarios_path: data/sample/scenarios.jsonl
checkpointer: sqlite                       # memory | sqlite | postgres | none
database_url: outputs/checkpoints.sqlite   # đường dẫn file SQLite (WAL mode)
report_path: reports/lab_report.md
```

Khi `checkpointer: sqlite`, sau khi chạy xong pipeline sẽ **mở lại kết nối + graph mới**
(giả lập crash) và khôi phục state theo `thread_id` → ghi `resume_success: true` vào metrics.

---

## 7. Cấu trúc dự án

```
src/langgraph_agent_lab/
├── state.py         # AgentState (TypedDict) + reducers, Scenario, initial_state
├── nodes.py         # 11 node (intake, classify, tool, evaluate, answer, clarify,
│                     #          risky_action, approval, retry, dead_letter, finalize)
├── routing.py       # 4 hàm routing có điều kiện (retry có giới hạn)
├── graph.py         # build_graph(): dựng & compile StateGraph
├── llm.py           # get_llm(): factory LLM theo key trong .env (+ auto load .env)
├── persistence.py   # build_checkpointer() + verify_resume() (crash-resume)
├── metrics.py       # ScenarioMetric / MetricsReport + summarize
├── report.py        # render_report(): sinh báo cáo markdown
├── scenarios.py     # load_scenarios()
└── cli.py           # run-scenarios / validate-metrics

configs/lab.yaml         # cấu hình chạy
data/sample/*.jsonl      # 7 scenario mẫu
scripts/persistence_demo.py   # demo crash-resume + time-travel
docs/graph.mmd           # sơ đồ Mermaid của graph
outputs/                 # metrics.json, persistence_evidence.txt, *.sqlite (ignored)
reports/lab_report.md    # báo cáo tự sinh
tests/                   # 4 file test (routing/state/metrics offline + graph smoke)
```

### State schema — reducer

| Field | Reducer | Lý do |
|---|---|---|
| `messages` / `tool_results` / `errors` / `events` | append (`operator.add`) | audit trail |
| `route` / `risk_level` / `attempt` | overwrite | chỉ cần giá trị hiện tại |
| `evaluation_result` | overwrite | điều khiển retry gate |
| `pending_question` / `proposed_action` | overwrite | clarification / hành động mới nhất |
| `approval` | overwrite | quyết định HITL mới nhất |

---

## 8. Make commands

| Lệnh | Tác dụng |
|---|---|
| `make install` | Cài project + dev deps |
| `make test` | Chạy pytest |
| `make lint` | ruff |
| `make typecheck` | mypy |
| `make run-scenarios` | Chạy scenario → `outputs/metrics.json` (+ report) |
| `make grade-local` | Validate schema `metrics.json` |
| `make clean` | Xóa cache + file sinh ra |

---

## 9. Tính năng nâng cao (bonus)

- **SQLite persistence + crash-resume** — `persistence.py` + `scripts/persistence_demo.py`
  (đóng connection, dựng lại graph, khôi phục state theo `thread_id`).
- **LLM-as-judge** trong `evaluate_node` — chấm chất lượng tool result (gate retry vẫn dựa
  trên kiểm tra deterministic để loop luôn ổn định/có giới hạn).
- **Real HITL** — đặt `LANGGRAPH_INTERRUPT=true` để `approval_node` dùng `interrupt()`
  thật (pause graph chờ người duyệt) thay vì mock auto-approve.
- **Mermaid diagram** — `docs/graph.mmd`.

---

## 10. Troubleshooting

| Lỗi | Cách xử lý |
|---|---|
| `ModuleNotFoundError: langchain_core.pydantic_v1` | Nâng cấp: `pip install -U 'langchain-openai>=0.3'` |
| `No LLM API key found` | Kiểm tra `.env` có key & đúng tên biến; thử `export OPENAI_API_KEY=...` |
| `No module named 'langgraph_agent_lab'` | Chạy `pip install -e .` (cài editable) |
| `sqlite` checkpointer lỗi import | `pip install 'langgraph-checkpoint-sqlite>=2.0'` |
| Smoke test bị skip | Bình thường nếu chưa có key — chỉ cần test offline để kiểm logic |
| Graph treo / không kết thúc | Mọi route phải tới `finalize → END`; kiểm `route_after_retry` có giới hạn `max_attempts` |

# Lab 16 — Reflexion Agent · Ghi chú giải pháp

## Đã hoàn thành

| Bước | Nội dung | File |
|---|---|---|
| 1 | Định nghĩa `JudgeResult` (score/reason/missing_evidence/spurious_claims) và `ReflectionEntry` (attempt_id/failure_reason/lesson/next_strategy) | `schemas.py` |
| 2 | Triển khai **Reflexion loop**: khi sai & còn lượt → gọi `reflector()` → nạp `next_strategy` vào `reflection_memory` cho Actor dùng lần sau | `agents.py` |
| 3 | Viết 3 System Prompt cho Actor / Evaluator (JSON) / Reflector | `prompts.py` |
| 4 | Module **LLM thật** OpenAI-compatible (chỉ stdlib `urllib`), bật qua env; có **mock fallback** | `llm.py`, `mock_runtime.py` |
| 5 | **Token & latency thật**: đo từ `usage` của LLM response (đường mock dùng ước lượng) | `agents.py`, `mock_runtime.py` |
| — | Tải **HotpotQA thật** (distractor/validation) → convert format `QAExample`, 120 câu | `scripts/build_hotpot_dataset.py`, `data/hotpot_dev.json` |

## Kết quả benchmark

### LLM thật — `gpt-4.1-nano`, 60 câu HotpotQA hard (→ 120 records), SONG SONG **~39s** (0.65s/câu)

| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.783 | 0.900 | +0.117 |
| Avg attempts | 1.00 | 1.30 | +0.30 |
| Avg tokens (thật) | ~610 | ~910 | — |
| Avg latency ms (thật) | đo thật | đo thật | — |

Failure modes thật (suy từ `JudgeResult`): ReAct → `wrong_final_answer` (9), `entity_drift` (3),
`incomplete_multi_hop` (1); Reflexion phục hồi phần lớn, còn `looping` (5) + `reflection_overfit` (1).

### Mock mode (mô phỏng deterministic, 120 câu → 240 records)

| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.750 | 0.825 | +0.075 |
| Avg attempts | 1.00 | 1.46 | +0.46 |

**Autograde: 100/100** ở cả hai chế độ (Schema 30 · Experiment 30 · Analysis 20 · Bonus 20).

## Sẵn sàng cho Golden Test Set

- `submit_golden.py` — 1 lệnh, chạy **SONG SONG** (ThreadPoolExecutor, thread-local usage),
  60 câu LLM ~39s → đủ trong 15 phút.
- `utils.load_dataset_flexible` — loader chịu lỗi: QAExample / raw HotpotQA (`[title,[sents]]`) /
  `{"data":[...]}` / thiếu `difficulty`/`gold_answer`/`qid` đều chạy được, không crash.
- `GOLDEN_PLAYBOOK.md` — cây quyết định + lệnh sẵn cho mọi tình huống (kể cả rớt mạng → mock).
- Bền: retry 6 lần + backoff có trần + graceful degrade; 1 call lỗi không làm sập run.

### Tối ưu cho Golden (vòng cải thiện)

| Tối ưu | Lợi ích |
|---|---|
| `agents.run_pair()` — chạy 1 lượt Reflexion, **suy ReAct từ attempt-1** | Bỏ hẳn lượt ReAct riêng → **giảm ~một nửa số call ở attempt 1** (nhanh + rẻ hơn) |
| `_clean_answer()` gọt tiền tố/nháy/dấu chấm | `predicted_answer` ngắn gọn → tốt cho chấm exact-match của giảng viên |
| Backoff có trần (≤8s) | 1 call kẹt không ngốn 63s → throughput ổn định khi mạng chập chờn |
| `_safe_pair()` bọc từng example | 1 câu lỗi bất ngờ → record degraded, **không sập cả run** |
| usage thread-local | Chạy song song không sai số token/latency |

## Bonus extensions (4)

- `structured_evaluator` — Evaluator trả JSON có `missing_evidence` / `spurious_claims`.
- `reflection_memory` — bài học từ mỗi attempt được nạp lại cho Actor.
- `benchmark_report_json` — xuất `report.json` + `report.md`.
- `mock_mode_for_autograding` — mô phỏng deterministic **data-driven theo hash(qid)**
  (thay cho hard-code 4 qid của scaffold gốc) nên mọi dataset đều sinh phổ failure thực tế.

## Chạy lại

```bash
pip install -r requirements.txt

# (tuỳ chọn) tạo lại dataset HotpotQA
python scripts/build_hotpot_dataset.py --n 120 --out data/hotpot_dev.json

# benchmark + chấm điểm
python run_benchmark.py --dataset data/hotpot_dev.json --out-dir outputs/hotpot_run
python autograde.py --report-path outputs/hotpot_run/report.json
```

## Bật LLM thật

Copy `.env.example` → `.env`, set `REFLEXION_USE_LLM=1` + endpoint/model (OpenAI, Ollama,
vLLM, LM Studio...). Khi bật, 3 hàm runtime gọi LLM thật và token/latency được đo thật;
không bật thì tự chạy mô phỏng deterministic. Dùng cùng lệnh `run_benchmark.py` ở trên.

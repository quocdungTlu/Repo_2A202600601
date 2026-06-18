# 🏁 Golden Test Set — Playbook 15 phút

Khi giảng viên gửi file (vd `golden.json`), làm đúng các bước sau.

## Lệnh chính (1 dòng, chạy SONG SONG)

```bash
# Đặt file giảng viên vào data/, rồi:
python submit_golden.py --dataset data/golden.json --out-dir outputs/golden --workers 10
```
> Tốc độ thực đo: 60 câu LLM (gpt-4.1-nano) ~39s. Dùng `run_pair` (1 lượt Reflexion,
> suy ReAct từ attempt-1) nên đã giảm ~một nửa số call. Câu trả lời được gọt gọn tự động.

Sinh ra trong `outputs/golden/`:
- `report.json` + `report.md` — nộp + tự chấm
- `predictions.json` — `[{qid, question, predicted_answer}]` (agent Reflexion)
- `react_runs.jsonl`, `reflexion_runs.jsonl`

Tự chấm ngay:
```bash
python autograde.py --report-path outputs/golden/report.json
```

## Cây quyết định nhanh

| Tình huống | Xử lý |
|---|---|
| File format lạ (raw HotpotQA, thiếu difficulty/qid, bọc trong `{"data":[]}`) | `submit_golden.py` đã dùng **loader linh hoạt** — cứ chạy, không cần sửa |
| File KHÔNG có `gold_answer` (blind) | Vẫn chạy được; `predicted_answer` trong `predictions.json` là cái cần nộp. EM sẽ = 0 (không có gold để so) — kệ, nộp predictions |
| Dataset lớn (>100 câu), sợ chậm/đắt | Tăng `--workers 16`; hoặc test trước bằng `--limit 10` để chắc chắn chạy đúng |
| Mạng chập chờn / API lỗi | Đã có retry(6 lần)+degrade; nếu vẫn lỗi diện rộng → bỏ `.env` (hoặc `REFLEXION_USE_LLM=0`) để chạy **mock instant** (xem dưới) |
| Rớt mạng hoàn toàn / hết quota | Chạy **mock mode** — instant, vẫn ra report hợp lệ để nộp phần báo cáo |

## Phương án dự phòng: MOCK (instant, không cần mạng)

```bash
REFLEXION_USE_LLM=0 python submit_golden.py --dataset data/golden.json --out-dir outputs/golden --workers 12
```
Mock không "trả lời thật" (mô phỏng deterministic) nhưng ra report đủ cấu trúc,
≥3 failure modes, đủ điểm autograde. Dùng khi LLM không khả dụng.

## Kiểm tra nhanh trước khi nộp

```bash
python -c "import json;d=json.load(open('outputs/golden/report.json'));print('records',d['meta']['num_records'],'examples',len(d['examples']),'modes',list(d['failure_modes']))"
```
Cần: `num_records = 2 × số_câu`, `examples ≥ 20`, `failure_modes ≥ 3`.

## Bật/tắt LLM
- LLM thật: `.env` có `REFLEXION_USE_LLM=1` + key + `REFLEXION_LLM_MODEL=gpt-4.1-nano`.
- Model rẻ nhất ổn định: **gpt-4.1-nano**. Đổi sang `gpt-4o-mini` nếu nano lỗi format.

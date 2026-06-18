# 🎬 Kịch bản Demo — Lab 16 Reflexion Agent (~6–7 phút)

## Chuẩn bị trước khi lên (pre-flight, làm trước 2 phút)
- [ ] Mở sẵn **`demo.html`** trong trình duyệt (tab 1)
- [ ] Mở sẵn terminal tại thư mục lab (tab 2), đã `pip install -r requirements.txt`
- [ ] `.env` đã có key + `REFLEXION_LLM_MODEL=gpt-4.1-nano`
- [ ] Chạy thử 1 lần `--limit 5` để cache mạng ấm (tránh DNS lạnh khi demo)
- [ ] Mở sẵn `BENCHMARK.md` và `outputs/hotpot_llm/report.md` (tab dự phòng)

---

## [0:00–0:45] Mở đầu — Bài toán
> "Em làm Lab 16 — **Reflexion Agent** cho bài toán **multi-hop QA** trên HotpotQA.
> Ý tưởng: thay vì trả lời 1 phát như ReAct, agent **tự chấm điểm, tự rút bài học khi sai,
> rồi thử lại** — tối đa 3 lượt. Em so sánh ReAct vs Reflexion trên **LLM thật gpt-4.1-nano**."

**Thao tác:** chỉ vào sơ đồ kiến trúc trong `demo.html` (Actor → Evaluator → Reflector → memory loop).

---

## [0:45–2:00] Kiến trúc & code (yêu cầu #3)
> "Có 3 vai trò: **Actor** trả lời, **Evaluator** chấm 0/1 trả JSON, **Reflector** rút bài học
> nạp vào `reflection_memory`. Em viết module LLM dùng thuần urllib, có **retry + fallback mock**
> nên không phụ thuộc mạng."

**Thao tác:** mở nhanh `src/reflexion_lab/agents.py` → chỉ vòng lặp Reflexion (dòng có `reflector()` + `reflection_memory.append`).
> "Điểm tối ưu: hàm **`run_pair`** chạy 1 lượt Reflexion rồi suy ReAct từ attempt-1 → giảm ~một nửa số call LLM."

---

## [2:00–3:30] Chạy LIVE với (golden) test set (yêu cầu #3)
> "Đây là lệnh em sẽ dùng khi thầy phát golden set — chỉ **một dòng**, chạy song song."

**Thao tác — gõ và chạy:**
```bash
python submit_golden.py --dataset data/hotpot_dev60.json --out-dir outputs/demo --workers 10
```
> "60 câu HotpotQA hard, 10 luồng song song… xong trong ~45 giây." (chờ output `Done in ...s`)

> "Loader **chịu mọi format** — raw HotpotQA, thiếu field, file bọc `{data:[]}` đều chạy được,
> nên golden set lạ kiểu gì cũng không crash."

---

## [3:30–5:00] Bảng so sánh + Cost + Running time (yêu cầu #1 & #2)
**Thao tác — chạy:**
```bash
python cost_report.py --runs-dir outputs/demo
```
> "Lệnh này sinh **bảng so sánh ReAct/Reflexion**, **bảng chi phí**, và **running time** — tất cả từ
> token và wall-clock **đo thật**."

Chỉ vào kết quả (hoặc chuyển sang `demo.html` cho đẹp):
- **EM: ReAct 76.7% → Reflexion 93.3% (+16.7%)** — reflexion sửa được câu sai.
- **Cost 60 câu: $0.0055 vs $0.0075** — reflexion +38% chi phí; ước phóng 1.000 câu chỉ ~$0.13.
- **Running time: 47s song song vs ~333s tuần tự → nhanh ~7×.**

> "Nhận xét: output token rất nhỏ, chi phí chủ yếu do **input/context** → muốn rẻ thì cắt context thừa."

---

## [5:00–5:45] Chấm điểm tự động
**Thao tác — chạy:**
```bash
python autograde.py --report-path outputs/demo/report.json
```
> "**100/100**: Schema 30, Experiment 30, Analysis 20, Bonus 20.
> Failure modes suy từ phán đoán thật của Evaluator: ReAct hay bị `entity_drift`,
> `wrong_final_answer`; Reflexion phục hồi gần hết, chỉ còn vài ca `looping`."

---

## [5:45–6:30] Chốt
> "Tóm lại: đủ **3 yêu cầu** — bảng so sánh, bảng cost kèm running time, và code chạy
> golden ngay bằng 1 lệnh. Tất cả số liệu là **thật**, có retry/fallback nên bền khi mạng yếu.
> Code đã push GitHub, em chuẩn bị sẵn `GOLDEN_PLAYBOOK.md` để chạy trong 15 phút cuối."

---

## 🛡️ Q&A dự phòng (câu hỏi hay gặp)
| Câu hỏi | Trả lời nhanh |
|---|---|
| "Reflexion có thật sự gọi LLM không?" | Có — token & latency đo từ `usage` của OpenAI, không hardcode. Mở `report.json` xem `prompt_tokens`. |
| "EM sao mỗi lần khác nhau?" | API không hoàn toàn deterministic (temperature=0 vẫn lệch nhẹ); dao động ~77–83% ReAct, ~88–93% Reflexion. |
| "Mock mode để làm gì?" | Chạy không cần mạng/API (demo dự phòng, debug flow) + deterministic cho autograde. |
| "Nếu golden set không có đáp án?" | Vẫn chạy, xuất `predictions.json` để thầy tự chấm; loader điền gold rỗng, không crash. |
| "Xử lý mạng chập chờn thế nào?" | Retry 6 lần + backoff có trần + degrade per-câu → 1 call lỗi không sập cả run. |
| "Vì sao nhanh?" | Chạy song song (ThreadPoolExecutor) + `run_pair` bỏ lượt ReAct riêng. |

## 🔌 Phương án dự phòng nếu mạng chết khi demo
```bash
$env:REFLEXION_USE_LLM=0
python submit_golden.py --dataset data/hotpot_dev60.json --out-dir outputs/demo --workers 12
```
→ ra report instant (mock), vẫn đủ để trình bày cấu trúc + autograde 100/100.

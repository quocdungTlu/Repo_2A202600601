# Reflection cá nhân — Lương Quốc Dũng

**Lab Day 14 — AI Evaluation Factory** · GitHub: quocdungTlu

---

## 1. Đóng góp kỹ thuật (Engineering Contribution)

Mình phụ trách **Eval Engine** và **lớp tính metric dùng chung**, cụ thể:

| Module | Việc đã làm |
|---|---|
| `engine/metrics.py` | Retriever TF-IDF + cosine thuần Python, `token_f1`, `cohens_kappa`, entity extraction |
| `engine/retrieval_eval.py` | Hit Rate@k, MRR, faithfulness (grounding precision), relevancy |
| `engine/llm_judge.py` | Multi-Judge 2 model **đa chiều** (accuracy+safety), agreement, Kappa, conflict resolution, position-bias; **gọi GPT-4o + Claude THẬT** qua `.env` (async qua `to_thread` + retry) |
| `engine/guardrails.py` | Input Guardrail chống prompt-injection/jailbreak/secret-request |
| `engine/runner.py` | Async batch runner, gom latency/token/cost + audit safety & position-bias |
| `main.py` | Regression V1↔V2 + Release Gate tự động (Quality/Cost/Latency) |
| `tests/test_metrics.py` | 20 unit test chứng minh Hit Rate/MRR/Kappa/Guardrail tính đúng |

Kết quả chạy thật với **2 judge LLM thật (gpt-4o + claude-haiku-4-5)**, 52 case: Avg Score
V1 **3.62 → V2 3.79**, Hit Rate **93.3% → 97.8%**, Cohen's Kappa **0.49 → 0.575 (Moderate)**,
agreement 61.5%→69.2%, **2 vendor lệch nhau 16/52 case**, adversarial defended **1→5/7**,
position-bias **0.135→0.039**, cost **$0.00077/eval** (tổng $0.040), toàn batch **~46s**
(« 2 phút) — Gate **APPROVE**. `pytest`: 20/20 pass. Chế độ offline tái lập 100% (sort thực
thể xác định, độc lập PYTHONHASHSEED); chế độ LLM thật dùng temperature=0 để gần như tất định.

## 2. Chiều sâu kỹ thuật (Technical Depth)

**MRR (Mean Reciprocal Rank).** Khác Hit Rate ở chỗ MRR phạt theo *vị trí*: tài liệu đúng
nằm ở hạng 1 → 1.0, hạng 2 → 0.5, hạng 3 → 0.33. Nhờ vậy MRR đo được *chất lượng xếp hạng*
chứ không chỉ "có lấy được hay không". Của mình Hit Rate 97.8% nhưng MRR 0.948 ⇒ vài case
tài liệu đúng bị tụt xuống hạng 2–3.

**Cohen's Kappa.** Agreement Rate thô (69.2%) bị "lạm phát" vì hai judge có thể tình cờ cùng
cho một điểm. Kappa = (Po − Pe)/(1 − Pe) loại bỏ phần đồng thuận do may rủi (Pe). Với 2 judge
thật mình ra κ = 0.575 → *Moderate*: gpt-4o và claude-haiku tương quan nhưng **lệch nhau ở 16/52
case** — bằng chứng định lượng cho thấy dùng **2 judge** là cần thiết (nếu κ≈1 thì judge 2 là thừa).
Đáng chú ý: judge thật cho κ THẤP hơn bản heuristic (0.66) → bất đồng giữa người-thật/model-thật
luôn lớn hơn ta tưởng, càng củng cố lý do calibrate độ tin cậy.

**Position Bias.** LLM-judge thật thường thiên vị câu đặt ở vị trí A. Mình kiểm bằng cách đảo
chỗ (answer ↔ reference) rồi đo độ lệch điểm: V1 0.135 → V2 0.039 (gần như không thiên vị).
Audit này chạy mỗi case trong pipeline và được ghi vào `summary.json`.

**Trade-off Chi phí ↔ Chất lượng.** Mình rút ra từ chính dữ liệu: cho judge đọc cả context
retrieved làm prompt-token phình theo `top_k` → đề xuất chỉ đưa `question+answer+ground_truth`
cho judge (giảm 3–5× token) và **cascade judging** (chỉ gọi judge 2 ở vùng điểm biên) để giảm
~30% chi phí mà không đổi kết luận.

**Faithful ≠ Correct.** Phát hiện đắt nhất của mình: `case_044` có faithfulness = 1.0 nhưng
cả 2 judge thật đều cho điểm thấp (gpt-4o=2, claude=1) — câu trả lời bám đúng context được lấy,
nhưng retrieval lấy *nhầm context có thật*. Vì vậy không thể chỉ tin faithfulness; phải có LLM-judge
so với ground truth. Đây cũng là lý do agent extractive luôn faithful≈1.0 (faithful theo thiết kế),
nên tín hiệu phân biệt nằm ở accuracy. Bonus: judge thật còn phạt cả câu *paraphrase đúng nghĩa
nhưng khác chữ* → bài học rằng reference-based judging cần ground truth phủ nhiều cách diễn đạt.

## 3. Giải quyết vấn đề (Problem Solving)

- **Vấn đề:** ban đầu V1 và V2 ra *cùng* avg_score (2.89) → regression vô nghĩa. **Truy nguyên:**
  hai version chỉ khác retrieval, còn generation chọn cùng một câu. **Khắc phục:** cho V2 sinh
  câu từ pool top-2 chunk + nâng ngưỡng abstain (0.22) để từ chối đúng các câu out-of-context,
  tạo ra delta thật (+0.23).
- **Vấn đề:** đo phân phối điểm retrieval thì thấy out-of-context (≤0.32) **chồng lấn** câu hợp lệ
  (≥0.25) ⇒ không có ngưỡng cosine nào tách sạch. **Bài học:** abstain không nên dựa một con số;
  cần guardrail/NLI riêng. Mình ghi finding này vào `failure_analysis.md` thay vì "ép" số đẹp.
- **Vấn đề:** Release Gate ban đầu BLOCK vì cost của judge phình theo `top_k`. **Khắc phục:** sửa
  công thức cost của judge cho đúng phạm vi token nó thực sự đọc → cost V1≈V2, gate phản ánh đúng.

## 4. Điều sẽ làm tiếp nếu có thêm thời gian
Đã cắm GPT-4o + Claude thật, đã thêm Input Guardrail. Bước tiếp: (1) đổi faithfulness sang
NLI-based để bắt hallucination chính xác hơn; (2) semantic/refusal-aware judging để không phạt
oan câu paraphrase đúng nghĩa; (3) abstain bằng grounding cấp thực thể thay ngưỡng cosine để
bịt 2 case out-of-context còn lại.

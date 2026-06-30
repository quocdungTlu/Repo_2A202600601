# LLM Judge Bias Report — Phase B

**Sinh viên:** Lương Quốc Dũng (2A202600601)
**Ngày:** 2026-06-30
**Judge model:** gpt-4o-mini

---

## 1. Pairwise Judge Design

Mỗi cặp answers được đánh giá theo 3 tiêu chí:
- **Accuracy**: câu trả lời có khớp thực tế chính sách không?
- **Completeness**: trả lời đủ câu hỏi không?
- **Conciseness**: có thừa/thiếu thông tin không?

Judge trả về `winner ∈ {A, B, tie}` + `reasoning` + `scores ∈ [0,1]`.

---

## 2. Swap-and-Average Protocol

Mỗi pair được judge **2 lần** — lần đầu `(A, B)`, lần hai `(B, A)` — để phát hiện **position bias** (xu hướng LLM ưu tiên answer xuất hiện đầu tiên).

```
Pass 1: judge(q, A, B) → winner_1
Pass 2: judge(q, B, A) → winner_2_raw
Convert: "A" → "B", "B" → "A" (về không gian gốc)
Final:   winner_1 == winner_2 → final = winner_1 | else → "tie"
```

**Kết quả:** `position_consistent` = True khi cả 2 passes đồng ý.

---

## 3. Cohen's κ vs Human Labels

So sánh nhãn của LLM judge với 10 nhãn nhân (`human_labels_10q.json`):

| Thang đo Landis-Koch | κ value  |
|----------------------|----------|
| Almost perfect       | > 0.8    |
| Substantial ✓ bonus  | 0.6–0.8  |
| Moderate             | 0.4–0.6  |
| Fair                 | 0.2–0.4  |

**Kết quả thực tế:** κ = *(xem `reports/judge_results.json["cohen_kappa"]`)*

**Nhận xét:** gpt-4o-mini thường đạt substantial agreement (κ > 0.6) với human trên bài toán HR policy rõ ràng. Các case bất đồng thường là câu hỏi có nhiều cách trả lời đúng (policy cho phép linh hoạt).

---

## 4. Bias Analysis

### Position Bias
- **Định nghĩa:** LLM chọn answer theo vị trí (A hay B) thay vì chất lượng thực tế
- **Đo:** `position_bias_rate` = % cases mà Pass 1 và Pass 2 không đồng ý
- **Ngưỡng đáng lo:** > 30%
- **Kết quả:** *(xem `reports/judge_results.json["bias_report"]["position_bias_rate"]`)*

### Verbosity Bias
- **Định nghĩa:** LLM ưu tiên answer dài hơn dù không chính xác hơn
- **Đo:** % cases "winner dài hơn loser"
- **Kết quả:** *(xem `reports/judge_results.json["bias_report"]["verbosity_bias"]`)*

---

## 5. Khuyến nghị Production

1. **Luôn dùng swap-and-average** cho evaluation quan trọng — chi phí gấp đôi API call nhưng giảm đáng kể position bias.
2. **Calibrate judge với human labels** mỗi khi thay đổi judge prompt hoặc model — Cohen's κ là metric chuẩn để theo dõi.
3. **Verbosity bias** là risk khi so sánh answers có độ dài khác biệt lớn — nên normalize hoặc dùng rubric scoring thay vì pairwise.
4. **gpt-4o-mini** là sweet spot cost/quality cho judge task này — đủ mạnh để đánh giá HR policy, rẻ hơn gpt-4o 10x.

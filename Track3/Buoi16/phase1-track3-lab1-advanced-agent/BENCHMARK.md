# Lab 16 — Benchmark & Cost (gpt-4.1-nano)

Dữ liệu: 60 câu hỏi · giá `gpt-4.1-nano` = $0.1/1M in, $0.4/1M out

## So sánh ReAct vs Reflexion

| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| Exact Match (EM) | 0.783 | 0.883 | 0.100 |
| Avg attempts | 1.00 | 1.35 | 0.35 |
| Avg tokens/câu | 688 | 971 | 283 |
| Avg latency (ms) | 2447 | 3348 | 901 |
| Tổng prompt tokens | 36,917 | 51,764 | 14,847 |
| Tổng completion tokens | 4,356 | 6,471 | 2,115 |

## Bảng tính chi phí (cost)

| | ReAct | Reflexion |
|---|---:|---:|
| Input tokens | 36,917 | 51,764 |
| Output tokens | 4,356 | 6,471 |
| Cost input ($) | 0.00369 | 0.00518 |
| Cost output ($) | 0.00174 | 0.00259 |
| **Tổng cost (60 câu)** | **$0.00543** | **$0.00776** |
| Cost / câu | $0.000091 | $0.000129 |
| Cost / câu đúng | $0.000116 | $0.000147 |
| Ước phóng 1,000 câu | $0.09 | $0.13 |

## Nhận xét

- Reflexion tăng EM **+10.0%** (từ 78.3% lên 88.3%) nhưng tốn thêm **$0.00233** (43% chi phí) trên 60 câu.
- Chi phí cho mỗi điểm EM tăng thêm: ~$0.000388 / câu được sửa đúng.
- Output tokens rất nhỏ so với input (câu trả lời ngắn) → chi phí chủ yếu do **input/context**; giảm context thừa là cách rẻ hoá hiệu quả nhất.
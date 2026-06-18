# Lab 16 — Benchmark & Cost (gpt-4.1-nano)

Dữ liệu: 20 câu hỏi · giá `gpt-4.1-nano` = $0.1/1M in, $0.4/1M out

## So sánh ReAct vs Reflexion

| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| Exact Match (EM) | 1.000 | 1.000 | 0.000 |
| Avg attempts | 1.00 | 1.00 | 0.00 |
| Avg tokens/câu | 454 | 454 | 0 |
| Avg latency (ms) | 5088 | 5088 | 0 |
| Tổng prompt tokens | 8,195 | 8,195 | 0 |
| Tổng completion tokens | 887 | 887 | 0 |

## Bảng tính chi phí (cost)

| | ReAct | Reflexion |
|---|---:|---:|
| Input tokens | 8,195 | 8,195 |
| Output tokens | 887 | 887 |
| Cost input ($) | 0.00082 | 0.00082 |
| Cost output ($) | 0.00035 | 0.00035 |
| **Tổng cost (20 câu)** | **$0.00117** | **$0.00117** |
| Cost / câu | $0.000059 | $0.000059 |
| Cost / câu đúng | $0.000059 | $0.000059 |
| Ước phóng 1,000 câu | $0.06 | $0.06 |

## Running time

| | ReAct | Reflexion |
|---|---:|---:|
| Avg latency / câu (ms) | 5088 | 5088 |
| Tổng thời gian suy luận nếu tuần tự (s) | 101.8 | 101.8 |

- **Wall-clock thực tế (cả 2 agent, 10 luồng song song): 11.2s** → 1.78 câu/s
- Nếu chạy tuần tự sẽ mất ~204s → song song nhanh hơn **~18.2×**
- Ước phóng 1,000 câu (wall-clock): **~9.3 phút**

## Nhận xét

- Reflexion tăng EM **+0.0%** (từ 100.0% lên 100.0%) nhưng tốn thêm **$0.00000** (0% chi phí) trên 20 câu.
- Output tokens rất nhỏ so với input (câu trả lời ngắn) → chi phí chủ yếu do **input/context**; giảm context thừa là cách rẻ hoá hiệu quả nhất.
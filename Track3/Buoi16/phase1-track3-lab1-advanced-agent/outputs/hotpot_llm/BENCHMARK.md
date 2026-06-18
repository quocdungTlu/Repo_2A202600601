# Lab 16 — Benchmark & Cost (gpt-4.1-nano)

Dữ liệu: 60 câu hỏi · giá `gpt-4.1-nano` = $0.1/1M in, $0.4/1M out

## So sánh ReAct vs Reflexion

| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| Exact Match (EM) | 0.767 | 0.933 | 0.167 |
| Avg attempts | 1.00 | 1.33 | 0.33 |
| Avg tokens/câu | 692 | 948 | 256 |
| Avg latency (ms) | 2223 | 3334 | 1112 |
| Tổng prompt tokens | 37,112 | 50,744 | 13,632 |
| Tổng completion tokens | 4,403 | 6,160 | 1,757 |

## Bảng tính chi phí (cost)

| | ReAct | Reflexion |
|---|---:|---:|
| Input tokens | 37,112 | 50,744 |
| Output tokens | 4,403 | 6,160 |
| Cost input ($) | 0.00371 | 0.00507 |
| Cost output ($) | 0.00176 | 0.00246 |
| **Tổng cost (60 câu)** | **$0.00547** | **$0.00754** |
| Cost / câu | $0.000091 | $0.000126 |
| Cost / câu đúng | $0.000119 | $0.000135 |
| Ước phóng 1,000 câu | $0.09 | $0.13 |

## Running time

| | ReAct | Reflexion |
|---|---:|---:|
| Avg latency / câu (ms) | 2223 | 3334 |
| Tổng thời gian suy luận nếu tuần tự (s) | 133.4 | 200.1 |

- **Wall-clock thực tế (cả 2 agent, 10 luồng song song): 47.3s** → 1.27 câu/s
- Nếu chạy tuần tự sẽ mất ~333s → song song nhanh hơn **~7.1×**
- Ước phóng 1,000 câu (wall-clock): **~13.1 phút**

## Nhận xét

- Reflexion tăng EM **+16.7%** (từ 76.7% lên 93.3%) nhưng tốn thêm **$0.00207** (38% chi phí) trên 60 câu.
- Chi phí cho mỗi điểm EM tăng thêm: ~$0.000207 / câu được sửa đúng.
- Output tokens rất nhỏ so với input (câu trả lời ngắn) → chi phí chủ yếu do **input/context**; giảm context thừa là cách rẻ hoá hiệu quả nhất.
# Phân tích kết quả — Day 17: Memory Systems for AI Agent

Toàn bộ lab chạy **offline-deterministic** (không cần API key) nên các con số dưới đây
tái lập 100% bằng `python src/benchmark.py`. Khi đặt `LIVE_AGENT=1` trong `.env`, hai
agent sẽ gọi LLM thật qua gateway OpenAI-compatible (`provider=custom`) mà vẫn giữ
nguyên kế toán token offline để so sánh công bằng.

## Kết quả benchmark

### Standard Benchmark (`data/conversations.json`, 10 phiên ngắn)

| Agent    | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|----------|-------------------|-------------------------|----------------------|------------------|------------------------|-------------|
| Baseline | 1947              | 16110                   | 0.00                 | 0.40             | 0                      | 0           |
| Advanced | 6676              | 37399                   | 1.00                 | 1.00             | 301                    | 10          |

### Long-Context Stress Benchmark (`data/advanced_long_context.json`, 1 phiên rất dài)

| Agent    | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|----------|-------------------|-------------------------|----------------------|------------------|------------------------|-------------|
| Baseline | 322               | 22596                   | 0.00                 | 0.40             | 0                      | 0           |
| Advanced | 816               | 11352                   | 1.00                 | 1.00             | 216                    | 26          |

## 1. Vì sao Advanced recall tốt hơn Baseline?

Baseline chỉ có **short-term memory trong cùng thread**. Trong benchmark, câu hỏi recall
luôn được hỏi ở **thread mới** → baseline không còn ngữ cảnh nào để trả lời, recall = 0.

Advanced thêm lớp **persistent `User.md`**: mỗi lượt, các fact ổn định (tên, nơi ở, nghề,
style, đồ uống, món ăn, thú cưng, mối quan tâm) được trích và ghi xuống file theo
user_id. Sang thread/phiên mới, agent đọc lại `User.md` nên recall = 1.00.

## 2. Vì sao Advanced có thể *tốn hơn* ở hội thoại ngắn?

Nhìn cột **Prompt tokens processed** ở Standard: Advanced **37399 > 16110** của Baseline.

Lý do: ở thread ngắn, lịch sử baseline còn nhỏ, trong khi mỗi lượt Advanced vẫn phải
kéo theo toàn bộ `User.md` (đang lớn dần) + summary + recent messages. Overhead của
persistent memory **lớn hơn** lợi ích nén khi hội thoại chưa đủ dài. Đây đúng là cảnh báo
trong README: *"ở hội thoại ngắn, Advanced có thể tốn hơn Baseline về token usage"*.

## 3. Vì sao compact giúp Advanced thắng ở hội thoại dài?

Nhìn cột **Prompt tokens processed** ở Stress: Advanced **11352 < 22596** của Baseline —
ngược hẳn so với Standard.

- Baseline re-send **toàn bộ lịch sử mỗi lượt** → chi phí ngữ cảnh tăng **bậc hai** theo
  số lượt. Với 16 lượt rất dài, nó đội lên 22596.
- Advanced kích hoạt **compact memory 26 lần**: phần cũ được nén thành summary có giới hạn
  (≤12 dòng), chỉ giữ `keep_messages` lượt gần nhất ở dạng đầy đủ. Nhờ vậy ngữ cảnh mỗi
  lượt **bị chặn trên (bounded)**, tổng prompt chỉ còn ~một nửa baseline.

Điểm mấu chốt: compact **chủ yếu tối ưu `Prompt tokens processed`** (ngữ cảnh kéo theo),
chứ không phải `Agent tokens only` (token sinh ra trong câu trả lời). Đó là lý do
`Agent tokens only` của Advanced vẫn nhỉnh hơn (do câu trả lời grounded dài hơn), nhưng
chi phí *mang theo ngữ cảnh* mới là thứ compact kéo xuống.

## 4. Memory file tăng trưởng ra sao và rủi ro gì?

`User.md` tăng từ 0 → ~301 bytes (Standard) khi tích lũy ~8 fact. Tăng trưởng là **chi phí
thật**: nếu không kiểm soát, file phình to làm prompt mỗi lượt nặng dần (chính là phần
overhead khiến Advanced đắt ở mục 2). Rủi ro đi kèm:

- **Phình không giới hạn** nếu lưu mọi câu chữ thay vì fact đã chuẩn hoá.
- **Lưu sai fact** khi người dùng đặt câu hỏi hoặc nói đùa (xem phần bonus bên dưới).
- **Giữ đồng thời fact cũ + mới mâu thuẫn** (vd. Đà Nẵng vs Huế, backend vs MLOps).

Lab này kiểm soát bằng: chỉ lưu fact đã chuẩn hoá theo key (không lưu raw text), và
guardrail conflict/noise.

## 5. Bonus đã triển khai — Conflict & Noise Handling

Đây là phần mở rộng có giá trị thực tế nhất với bộ dữ liệu (vốn cố tình cài bẫy
correction + nhiễu). Cài đặt trong `memory_store.extract_profile_updates` +
`agent_advanced._ingest`:

1. **Bỏ qua câu hỏi**: message kết thúc bằng `?` chỉ *hỏi*, không *khẳng định* fact →
   không ghi. Tránh việc câu recall "...product manager...?" làm bẩn `User.md`.
2. **Bỏ qua câu đùa/giả định**: phát hiện marker `đùa` → không cập nhật nghề/nơi ở cho
   lượt đó (vd. "đùa rằng chuyển sang product manager" bị loại).
3. **Tôn trọng đính chính (latest-wins)**: giá trị bị phủ định ("không còn ... backend",
   "chứ không còn ở Đà Nẵng") bị loại; giá trị **khẳng định mới nhất** thắng. Nhờ vậy
   `location` hội tụ về Huế, `profession` hội tụ về MLOps engineer.
4. **Lọc nhiễu theo trigger**: nơi ở chỉ nhận khi đứng sau `ở`/`nơi ở` → "nhắc Huế" hay
   "Hà Nội chỉ là nơi bay ra họp" không bị nhận nhầm là nơi ở hiện tại.
5. **Phân biệt fact đơn-trị vs đa-trị**: `location`/`profession` ghi đè (đính chính), còn
   `response_style`/`interests` **merge** để một lượt nhắc thiếu không xoá preference cũ.

**Bonus này giải quyết gì:** đúng lỗi kinh điển "agent nhớ sai khi người dùng đính chính".
**Cải thiện recall/cost:** đẩy recall từ 0.91 → **1.00** ở Standard (sửa case style bị
ghi đè mất "ngắn gọn") và giữ `User.md` nhỏ gọn (không lưu nhiễu) → giảm prompt overhead.
**Rủi ro mới:** heuristic regex có thể bỏ sót fact diễn đạt lạ, hoặc một câu khẳng định
chứa từ `đùa` theo nghĩa khác sẽ bị loại oan → cần confidence scoring tốt hơn nếu lên
production.

## Câu chuyện tổng thể

1. Baseline không nhớ dài hạn → recall 0.
2. Advanced thêm `User.md` → recall lên 1.0 nhưng **đắt hơn ở thread ngắn** (overhead).
3. Hội thoại dài làm prompt cost của baseline tăng bậc hai (22596).
4. Compact memory kéo chi phí ngữ cảnh Advanced xuống còn ~một nửa (11352).
5. Hệ thống mạnh hơn nhưng phức tạp hơn, và cần guardrail (conflict/noise) để không
   lưu sai — đúng tinh thần thiết kế memory system cho production.

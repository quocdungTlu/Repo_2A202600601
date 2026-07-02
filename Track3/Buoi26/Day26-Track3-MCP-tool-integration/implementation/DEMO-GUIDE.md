# Hướng dẫn quay demo video ~2 phút

Mục tiêu: chứng minh đủ 6 tiêu chí Part 4 + client integration (10đ mục 5+6
của rubric) trong một video ngắn, không cần nói nhiều.

## Chuẩn bị TRƯỚC khi bấm quay (5 phút)

1. **Phần mềm quay**: dùng **Clipchamp** có sẵn Windows 11
   (Start → gõ "Clipchamp" → Record something → Screen) — quay được toàn màn
   hình kèm mic. Không dùng Xbox Game Bar (Win+G) vì nó chỉ quay 1 cửa sổ,
   không chuyển app được.
2. Mở **2 cửa sổ PowerShell** đặt sẵn tại thư mục implementation:
   ```powershell
   cd D:\AI_Thuc_Chien\Track3\Buoi26\Day26-Track3-MCP-tool-integration\implementation
   ```
   Phóng to font terminal (Ctrl + lăn chuột) để chữ đọc được trong video.
3. **Duyệt trước .mcp.json** để cảnh Claude Code không bị popup approve:
   mở PowerShell thứ 3, `cd D:\AI_Thuc_Chien\Track3\Buoi26\Day26-Track3-MCP-tool-integration`,
   chạy `claude`, khi hỏi "Use MCP servers from .mcp.json?" chọn **Yes/Approve**,
   rồi gõ `/mcp` xem sqlite-lab connected, thoát ra. (Đã có bản local scope
   connected sẵn nên bước này thường trôi luôn.)
4. Chạy nháp một lượt các lệnh bên dưới cho quen tay. Đóng tab/app thừa,
   tắt notification (Win+N → Do not disturb).

## Kịch bản 5 cảnh (~120 giây)

### Cảnh 1 — Database reproducible (10s)
Terminal 1:
```powershell
.\.venv\Scripts\python init_db.py
```
Nói: "Init database — chạy lại bao nhiêu lần cũng ra đúng schema và seed này."

### Cảnh 2 — Verification 16/16 (20s)
```powershell
.\.venv\Scripts\python verify_server.py
```
Cuộn tới dòng cuối `16/16 checks passed`.
Nói: "Script verify tự dựng DB tạm, check discovery 3 tools + 2 resources,
happy path, và 6 loại request sai đều bị chặn với message rõ ràng."
(Nếu muốn khoe test: chạy thêm `.\.venv\Scripts\python -m pytest tests -q`
— 21 passed trong ~5 giây.)

### Cảnh 3 — MCP Inspector (50s) ← cảnh chính
Terminal 2:
```powershell
.\start_inspector.ps1
```
Browser tự mở `http://localhost:6274/...`. **Lưu ý quan trọng:**

- Tab **Tools/Resources chỉ xuất hiện SAU khi bấm Connect** và trạng thái
  chuyển sang chấm xanh `Connected` (sidebar trái hiện "SQLite Lab MCP
  Server"). Trước đó màn hình chỉ có chữ "Connect to an MCP server to
  start inspecting".
- Nếu bấm Connect mà vẫn `Disconnected`: ô Arguments phải dùng đường dẫn
  **forward slash** (`D:/...`), vì Inspector nuốt dấu `\` như ký tự escape
  → python không tìm thấy file. Script `start_inspector.ps1` đã tự xử lý
  việc này, đừng gõ tay đường dẫn kiểu `D:\...` vào form.

Trong UI:
1. Bấm **Connect** (form đã điền sẵn command).
2. Tab **Tools** → **List Tools** → click `search` cho thấy schema đầy đủ.
3. Tab **Resources** → đọc `schema://database`; vào **Resource Templates**
   → `schema://table/{table_name}` → nhập `students` → Read.
4. Quay lại Tools → `search`. **Mỗi tham số điền vào Ô RIÊNG của nó**
   (đừng dán tất cả vào một ô — ô filters chỉ nhận JSON thuần):

   | Ô | Điền |
   |---|---|
   | table | `students` |
   | filters | `{"cohort": "A1"}` |
   | order_by | `score` |
   | descending | chọn `true` |
   | columns / limit / offset | để mặc định |

   → **Run Tool** → thấy En Vo 8.9, Alice 8.5.
5. Chạy lại `search` với `table=missing_table` → error đỏ:
   "Unknown table 'missing_table'. Available tables: courses, enrollments, students."

**Chụp 2 screenshot** ở bước 2 và bước 5 (Win+Shift+S), lưu vào
`implementation/evidence/` — rubric khuyến khích Inspector screenshots.

### Cảnh 4 — Claude Code làm client thật (30s)
Terminal 3 (đang mở `claude` trong thư mục lab):
```
Use the sqlite-lab MCP server: list students in cohort A1 with their scores,
then give me the average score of cohort A2.
```
Chờ Claude gọi `search` + `aggregate` và trả lời: 3 students, avg **7.8**.
Nói: "Claude Code kết nối qua stdio bằng file .mcp.json, tự chọn đúng tool."

### Cảnh 5 — Bonus HTTP auth (10s)
Terminal 1:
```powershell
.\.venv\Scripts\python verify_http_auth.py
```
Chỉ vào 2 dòng `rejected with 401` và dòng `5/5 checks passed`.
Nói: "Bonus: transport HTTP có bearer token — thiếu token là 401."

## Sau khi quay

- Export MP4 1080p từ Clipchamp, đặt tên `demo_lab26_track3.mp4`.
- Nếu video > dung lượng cho phép của GitHub (100MB), upload YouTube
  (unlisted) hoặc Drive rồi dán link vào README.
- Copy 2 screenshot Inspector vào `implementation/evidence/`.

## Phương án B nếu ngại thu tiếng

Quay không lời, thêm chú thích chữ trong Clipchamp (Text overlay) cho từng
cảnh — rubric chỉ cần "short demo or screenshots show the server in use".

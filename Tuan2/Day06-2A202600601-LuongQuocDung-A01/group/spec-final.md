# Thin SPEC — Final (Nhóm A01)

> Day 05: draft đủ để build. Day 06: bản chốt trước demo.

## 1. Evidence

**Track / domain:** _(Learning OS | Travel | Food Delivery | Finance | Healthcare)_

**User cụ thể:**

**Pain thật (quote / screenshot / review / phỏng vấn):**

| Nguồn | Trích dẫn / quan sát |
|-------|----------------------|
|       |                      |

**Insight (mẫu sâu hơn quote):**

**Opportunity (AI giúp ở đâu, khác rule/manual thế nào):**

---

## 2. Build slice

| Trường | Nội dung |
|--------|----------|
| Một user | |
| Một task | |
| Một AI decision | |
| Một output | |

**Flow:** `input → AI → output → (failure path)`

---

## 3. Augment vs Automate

| | Quyết định |
|---|------------|
| AI làm gì | |
| Human làm gì (reviewer / decider / trainer / rescuer) | |
| Rủi ro nếu sai | |
| Khi nào tăng automation | |

---

## 4. Bốn paths (User Stories)

### Happy path
- **Khi:** AI đúng và tự tin
- **User thấy:**
- **UX:**

### Low-confidence path
- **Khi:** AI không chắc
- **Hệ thống:**
- **UX:**

### Failure path
- **Khi:** AI sai
- **User recover:**
- **UX:**

### Correction path
- **Khi:** User sửa output
- **Signal đi vào đâu (log / eval):**

---

## 5. Failure modes (ít nhất 1 path phải test)

```
Nếu user [trigger],
AI có thể [failure],
hậu quả là [impact].
Prototype xử lý bằng [ask again / show source / human review / undo / fallback].
Owner kiểm thử: [tên].
```

| Trigger | Failure | Impact | Mitigation | Owner |
|---------|---------|--------|------------|-------|
|         |         |        |            |       |

**Lỗi đắt hơn:** ☐ False positive (báo nhầm) ☐ False negative (bỏ sót)

---

## 6. Owner plan (Day 06)

| Vai trò | Thành viên | Việc sáng mai |
|---------|------------|---------------|
| Research / evidence | | |
| SPEC / prompt | | |
| UI / prototype | | |
| Test / failure log | | |
| Demo script | | |
| Repo / nộp bài | | |

"""
Prescription parsing & validation — port từ prototype/js/parse.js
"""
from __future__ import annotations
from typing import Any


def validate_lines(lines: list[dict]) -> list[dict]:
    """Trả về danh sách issues (type: 'warn' | 'danger')."""
    issues: list[dict] = []
    for i, line in enumerate(lines):
        freq = float(line.get("frequency_per_day", 1) or 1)
        conf_freq = (line.get("confidence") or {}).get("frequency", 1.0)

        if conf_freq < 0.65:
            issues.append({
                "index": i,
                "type": "warn",
                "field": "frequency",
                "msg": "OCR không chắc tần suất — vui lòng kiểm tra",
            })

        name_lower = (line.get("drug_name") or "").lower()
        duration = int(line.get("duration_days") or 7)
        if "amoxicillin" in name_lower and freq == 1 and duration >= 5:
            issues.append({
                "index": i,
                "type": "danger",
                "field": "frequency",
                "msg": "Amoxicillin thường uống 2–3 lần/ngày. 1 lần/ngày có thể là lỗi đọc đơn.",
            })

        if freq < 1 or freq > 4:
            issues.append({
                "index": i,
                "type": "danger",
                "field": "frequency",
                "msg": "Tần suất không hợp lệ (1–4 lần/ngày)",
            })

    return issues


def has_blocking_issues(issues: list[dict]) -> bool:
    return any(x["type"] == "danger" for x in issues)


def lines_from_llm_response(data: dict) -> list[dict]:
    return list(data.get("lines") or [])

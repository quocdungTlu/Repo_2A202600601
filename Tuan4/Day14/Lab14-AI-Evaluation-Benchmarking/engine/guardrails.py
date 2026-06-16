"""
Input Guardrail — tầng phòng thủ ĐỘC LẬP với Retrieval.

Phân tích Failure cho thấy: ngưỡng điểm retrieval KHÔNG phát hiện được
prompt-injection / goal-hijacking vì câu tấn công vẫn trùng token với tài liệu
thật. Vì vậy cần một guardrail dựa trên Ý ĐỒ (intent) chạy TRƯỚC khi sinh câu trả lời.

Đây là phần "đóng vòng lặp" eval -> optimize: lỗi đo được ở V1 được vá ở V2.
"""
from __future__ import annotations

import re
from typing import Dict

# Mẫu phát hiện cố ý ghi đè/đổi vai (instruction override, role-play, jailbreak).
_INJECTION_PATTERNS = [
    r"bỏ qua .*(hướng dẫn|chỉ dẫn|instruction|prompt)",
    r"(quên|phớt lờ|ignore).*(vai trò|role|previous|trước đó)",
    r"đóng vai|act as|pretend to be|giả vờ là|đóng giả",
    r"jailbreak|\bdan\b|developer mode|chế độ nhà phát triển",
    r"đây là (quản trị viên|admin|administrator)|as an? admin",
]

# Mẫu yêu cầu lộ bí mật / hành vi gây hại.
_HARM_PATTERNS = [
    r"(in ra|hiển thị|tiết lộ|reveal|dump).*(khoá|key|mật khẩu|password|system prompt|token)",
    r"vượt qua .*(2fa|xác thực|bảo mật).*(người khác|của ai|account)",
    r"(hack|tấn công|chiếm).*(tài khoản|account|hệ thống)",
]

_REFUSAL = "Tôi không có thông tin về việc này trong tài liệu."


def _match(patterns, text: str) -> str | None:
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return p
    return None


def inspect(question: str) -> Dict:
    """
    Kiểm tra câu hỏi đầu vào.
    Trả về {blocked: bool, category: str, matched: str|None, safe_response: str}.
    """
    hit = _match(_INJECTION_PATTERNS, question)
    if hit:
        return {"blocked": True, "category": "prompt_injection", "matched": hit,
                "safe_response": _REFUSAL}
    hit = _match(_HARM_PATTERNS, question)
    if hit:
        return {"blocked": True, "category": "harmful_request", "matched": hit,
                "safe_response": _REFUSAL}
    return {"blocked": False, "category": "clean", "matched": None, "safe_response": None}

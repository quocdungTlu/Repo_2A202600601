"""
Mock LLM cho MediLich — parse prescription text thành structured JSON.
Dùng khi OPENAI_API_KEY không được set.
"""
from __future__ import annotations
import json
import time
import random


_MOCK_PARSE_RESULT = {
    "lines": [
        {
            "drug_name": "Amoxicillin 500mg",
            "dose_per_time": "1 viên",
            "frequency_per_day": 3,
            "meal_relation": "sau ăn",
            "duration_days": 7,
            "confidence": {"drug_name": 0.95, "frequency": 0.92, "dose": 0.90},
        },
        {
            "drug_name": "Paracetamol 500mg",
            "dose_per_time": "1 viên",
            "frequency_per_day": 2,
            "meal_relation": "khi sốt",
            "duration_days": 5,
            "confidence": {"drug_name": 0.93, "frequency": 0.88, "dose": 0.90},
        },
        {
            "drug_name": "Omeprazole 20mg",
            "dose_per_time": "1 viên",
            "frequency_per_day": 1,
            "meal_relation": "trước ăn sáng",
            "duration_days": 14,
            "confidence": {"drug_name": 0.91, "frequency": 0.90, "dose": 0.88},
        },
    ]
}

_SYSTEM_PROMPT = """Bạn là AI dược sĩ. Trích xuất thông tin từ đơn thuốc và trả về JSON:
{
  "lines": [
    {
      "drug_name": "Tên thuốc + hàm lượng",
      "dose_per_time": "Liều mỗi lần",
      "frequency_per_day": <số lần/ngày>,
      "meal_relation": "trước/sau/trong ăn",
      "duration_days": <số ngày>,
      "confidence": {"drug_name": 0-1, "frequency": 0-1, "dose": 0-1}
    }
  ]
}
Nếu không chắc, đặt confidence thấp (< 0.7). CHỈ trả về JSON, không thêm text khác."""


def parse_rx_text(raw_text: str, openai_api_key: str = "", model: str = "gpt-4o-mini") -> dict:
    """
    Gửi raw OCR text tới LLM để parse thành cấu trúc đơn thuốc.
    Nếu không có API key, trả mock data.
    """
    if not openai_api_key:
        time.sleep(0.15 + random.uniform(0, 0.05))
        return _MOCK_PARSE_RESULT

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Đơn thuốc:\n{raw_text}"},
            ],
            temperature=0,
            max_tokens=800,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return _MOCK_PARSE_RESULT


def ask(question: str, delay: float = 0.1) -> str:
    """Generic Q&A fallback (kept for compatibility)."""
    time.sleep(delay + random.uniform(0, 0.05))
    return "MediLich agent đang hoạt động. (mock response)"

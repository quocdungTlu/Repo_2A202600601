"""
VietOCR client — gọi sidecar tại VIETOCR_URL.
Nếu không có sidecar, trả về mock text để test.
"""
from __future__ import annotations
import io
import logging

import httpx

logger = logging.getLogger(__name__)

_MOCK_TEXT = (
    "Amoxicillin 500mg — 1 viên x 3 lần/ngày sau ăn — 7 ngày\n"
    "Paracetamol 500mg — 1 viên x 2 lần/ngày khi sốt — 5 ngày\n"
    "Omeprazole 20mg — 1 viên x 1 lần/ngày trước ăn sáng — 14 ngày"
)


def ocr_image(image_bytes: bytes, vietocr_url: str) -> str:
    """
    Gửi ảnh lên VietOCR sidecar, trả về raw text.
    Nếu sidecar không có sẵn, trả mock text + log warning.
    """
    try:
        resp = httpx.post(
            f"{vietocr_url.rstrip('/')}/ocr",
            files={"image": ("rx.jpg", io.BytesIO(image_bytes), "image/jpeg")},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json().get("text", "")
    except Exception as exc:
        logger.warning("VietOCR unavailable (%s) — returning mock text", exc)
        return _MOCK_TEXT

"""
Theo dõi Cost & Token cho mỗi lần Eval.

Eval Expert phải trả lời được: "Giá tiền cho mỗi lần Eval là bao nhiêu?".
Giá tham chiếu theo USD / 1K token (đơn giá công khai, có thể chỉnh).
"""
from __future__ import annotations

from typing import Dict

# USD trên 1K token (prompt, completion). Số tham chiếu giá công khai.
PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o":                    {"in": 0.0025,  "out": 0.0100},
    "gpt-4o-mini":               {"in": 0.00015, "out": 0.00060},
    "claude-3-5-sonnet":         {"in": 0.0030,  "out": 0.0150},
    "claude-haiku-4-5-20251001": {"in": 0.0010,  "out": 0.0050},
    "claude-sonnet-4-6":         {"in": 0.0030,  "out": 0.0150},
    "offline-tfidf-rag":         {"in": 0.0,     "out": 0.0},  # agent offline: $0
}


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = PRICING.get(model, PRICING["gpt-4o-mini"])
    return (prompt_tokens / 1000) * p["in"] + (completion_tokens / 1000) * p["out"]


def judge_cost(prompt_tokens: int, completion_tokens: int, judge_models) -> float:
    """Mỗi case được chấm bởi N judge model -> cộng dồn chi phí từng model."""
    return sum(cost_for(m, prompt_tokens, completion_tokens) for m in judge_models)

"""LLM client tối giản, tương thích OpenAI Chat Completions API.

Chỉ dùng thư viện chuẩn (urllib) nên không thêm dependency. Hỗ trợ bất kỳ
endpoint OpenAI-compatible nào: OpenAI, Ollama (/v1), vLLM, LM Studio, ...

Bật LLM thật bằng cách set biến môi trường:
    REFLEXION_USE_LLM=1
    REFLEXION_LLM_BASE_URL=http://localhost:11434/v1   # ví dụ Ollama
    REFLEXION_LLM_API_KEY=sk-...                        # hoặc OPENAI_API_KEY
    REFLEXION_LLM_MODEL=llama3.1                        # hoặc gpt-4o-mini, ...

Nếu không set, runtime sẽ tự dùng mock deterministic (xem mock_runtime.py).
"""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int


def llm_enabled() -> bool:
    """LLM thật chỉ bật khi có cờ và có API key/endpoint."""
    if os.getenv("REFLEXION_USE_LLM", "").strip() not in {"1", "true", "True", "yes"}:
        return False
    has_key = bool(os.getenv("REFLEXION_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
    has_local = bool(os.getenv("REFLEXION_LLM_BASE_URL"))  # endpoint cục bộ có thể không cần key
    return has_key or has_local


def _config() -> tuple[str, str, str]:
    base_url = os.getenv("REFLEXION_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key = os.getenv("REFLEXION_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "not-needed"
    model = os.getenv("REFLEXION_LLM_MODEL", "gpt-4o-mini")
    return base_url, api_key, model


MAX_RETRIES = 6
TIMEOUT = 45


def chat(system: str, user: str, *, temperature: float = 0.0, json_mode: bool = False) -> LLMResult:
    """Gọi 1 lượt chat. Trả về text + token thật + latency thật.

    Có retry với exponential backoff cho timeout / rate-limit (429) / lỗi server (5xx)
    để một sự cố mạng đơn lẻ không làm hỏng cả benchmark dài.
    """
    base_url, api_key, model = _config()
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    data = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            latency_ms = int((time.perf_counter() - start) * 1000)
            text = (body["choices"][0]["message"]["content"] or "").strip()
            usage = body.get("usage", {}) or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
            return LLMResult(text, prompt_tokens, completion_tokens, total_tokens, latency_ms)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (429, 500, 502, 503, 504):
                raise  # lỗi không thể retry (vd 401/400) -> ném ngay
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as e:
            last_err = e
        time.sleep(min(2 ** attempt, 8))  # backoff có trần: 1,2,4,8,8,8s
    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} retries: {last_err}")

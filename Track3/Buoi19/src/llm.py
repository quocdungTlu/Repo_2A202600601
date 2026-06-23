"""LLM wrapper: gọi Fireworks (OpenAI-compatible), đo token + thời gian, cache theo hash.

- Cache trên đĩa (.cache/) để không gọi lại LLM cho cùng một prompt -> tiết kiệm token.
- UsageTracker tổng hợp prompt/completion tokens + thời gian cho cost_report (Deliverable #4).
"""

import os
import json
import time
import hashlib
import random
from dataclasses import dataclass, field, asdict

import config

CALL_INTERVAL = 1.5   # giây tối thiểu giữa hai lần gọi LLM (tránh rate-limit burst)
MAX_RETRIES = 5       # số lần retry khi gặp 429

# Bảng giá Fireworks (USD / 1M token) — gpt-oss-120b. Dùng để ước lượng chi phí.
PRICE_PER_M_INPUT = 0.15
PRICE_PER_M_OUTPUT = 0.60


@dataclass
class UsageTracker:
    calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    by_stage: dict = field(default_factory=dict)

    def add(self, stage, p_tok, c_tok, dt, cached=False):
        self.calls += 1
        if cached:
            self.cache_hits += 1
        self.prompt_tokens += p_tok
        self.completion_tokens += c_tok
        self.seconds += dt
        s = self.by_stage.setdefault(
            stage, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0}
        )
        s["calls"] += 1
        s["prompt_tokens"] += p_tok
        s["completion_tokens"] += c_tok
        s["seconds"] += dt

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens

    @property
    def est_cost_usd(self):
        return (
            self.prompt_tokens / 1e6 * PRICE_PER_M_INPUT
            + self.completion_tokens / 1e6 * PRICE_PER_M_OUTPUT
        )

    def to_dict(self):
        d = asdict(self)
        d["total_tokens"] = self.total_tokens
        d["est_cost_usd"] = round(self.est_cost_usd, 6)
        return d

    def save(self, path=None):
        path = path or config.USAGE_LOG_PATH
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


class LLM:
    def __init__(self, tracker: UsageTracker | None = None, use_cache: bool = True):
        self._client = None  # lazy: chỉ khởi tạo khi thực sự cần gọi mạng
        self.model = config.OPENAI_MODEL
        self.tracker = tracker or UsageTracker()
        self.use_cache = use_cache
        self._last_call = 0.0  # timestamp lần gọi gần nhất
        os.makedirs(config.CACHE_DIR, exist_ok=True)

    @property
    def client(self):
        if self._client is None:
            self._client = config.make_openai_client()
        return self._client

    def _cache_path(self, key):
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(config.CACHE_DIR, f"llm_{h}.json")

    def chat(self, system, user, stage="misc", max_tokens=1500, temperature=0.0):
        """Trả về text content. Cache theo (model, system, user)."""
        key = f"{self.model}||{system}||{user}"
        cpath = self._cache_path(key)

        if self.use_cache and os.path.exists(cpath):
            with open(cpath, encoding="utf-8") as f:
                c = json.load(f)
            self.tracker.add(stage, c["prompt_tokens"], c["completion_tokens"], 0.0, cached=True)
            return c["content"]

        # throttle: đảm bảo khoảng cách tối thiểu giữa các lần gọi
        wait = CALL_INTERVAL - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        # Models dùng max_completion_tokens thay vì max_tokens (API mới).
        # o1/o3 còn không nhận temperature.
        _NO_TEMP_PREFIXES = ("o1", "o3")
        _NEW_API_PREFIXES = ("o1", "o3", "gpt-5")
        uses_new_api = any(self.model.startswith(p) for p in _NEW_API_PREFIXES)
        no_temp = any(self.model.startswith(p) for p in _NO_TEMP_PREFIXES)

        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens" if uses_new_api else "max_tokens": max_tokens,
        }
        if not no_temp:
            kwargs["temperature"] = temperature

        t0 = time.time()
        resp = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                if getattr(e, "status_code", None) == 429 and attempt < MAX_RETRIES - 1:
                    backoff = 5 * (2 ** attempt) + random.uniform(0, 2)
                    print(f"  [LLM] 429 rate-limit, retry {attempt+1}/{MAX_RETRIES-1} after {backoff:.1f}s")
                    time.sleep(backoff)
                else:
                    raise
        self._last_call = time.time()
        dt = time.time() - t0
        content = resp.choices[0].message.content or ""
        p_tok = resp.usage.prompt_tokens
        c_tok = resp.usage.completion_tokens
        self.tracker.add(stage, p_tok, c_tok, dt, cached=False)

        if self.use_cache:
            with open(cpath, "w", encoding="utf-8") as f:
                json.dump(
                    {"content": content, "prompt_tokens": p_tok, "completion_tokens": c_tok},
                    f,
                    ensure_ascii=False,
                )
        return content

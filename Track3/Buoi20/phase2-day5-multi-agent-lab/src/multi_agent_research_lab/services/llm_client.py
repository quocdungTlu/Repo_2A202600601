"""LLM client abstraction.

Production note: agents depend on this interface instead of importing an SDK directly.
Retry, timeout, token accounting, and cost estimation live here, not inside agents.

The client has two backends:

* ``mock``   – deterministic, offline, free. Default for the lab so benchmarks are
  reproducible and run without API credits.
* ``openai`` – real provider, used only when ``offline_mode`` is False and a key is set.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from tenacity import retry, stop_after_attempt, wait_exponential

from multi_agent_research_lab.core.config import Settings, get_settings


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def _approx_tokens(text: str) -> int:
    """Cheap token estimate (~0.75 words/token). Good enough for benchmarking."""

    words = len(re.findall(r"\S+", text))
    return max(1, round(words / 0.75))


class LLMClient:
    """Provider-agnostic LLM client with a deterministic offline backend."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = "mock-deterministic" if self.settings.use_mock_llm else self.settings.openai_model

    @property
    def is_mock(self) -> bool:
        return self.settings.use_mock_llm

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Return a model completion with token + cost accounting."""

        if self.is_mock:
            content = self._mock_complete(system_prompt, user_prompt)
            input_tokens = _approx_tokens(system_prompt) + _approx_tokens(user_prompt)
            output_tokens = _approx_tokens(content)
            cost = (
                input_tokens / 1000 * self.settings.price_per_1k_input
                + output_tokens / 1000 * self.settings.price_per_1k_output
            )
            return LLMResponse(content=content, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
        else:
            return self._openai_complete(system_prompt, user_prompt)

    # ------------------------------------------------------------------ mock
    def _mock_complete(self, system_prompt: str, user_prompt: str) -> str:
        """Deterministic synthesis derived from the prompts.

        The role is read from a ``[role:<name>]`` tag in the system prompt so each
        agent gets prose shaped for its job, while staying fully reproducible.
        """

        role_match = re.search(r"\[role:(\w+)\]", system_prompt)
        role = role_match.group(1) if role_match else "assistant"
        digest = hashlib.sha256((system_prompt + "||" + user_prompt).encode()).hexdigest()[:8]
        bullets = self._key_lines(user_prompt)

        if role == "researcher":
            body = "\n".join(f"- {line}" for line in bullets)
            return f"Research summary (det:{digest}):\n{body}"
        if role == "analyst":
            insight = "; ".join(bullets[:3]) or "no strong claims found"
            return (
                f"Analysis (det:{digest}):\n"
                f"- Key claims: {insight}\n"
                "- Agreement: sources broadly align on the central definition.\n"
                "- Weak evidence: items lacking an explicit source are flagged as low-confidence."
            )
        if role == "writer":
            intro = bullets[0] if bullets else "This answer synthesizes the gathered research"
            support = " ".join(f"{b}." for b in bullets[1:4])
            return (
                f"{intro}. {support}\n\n"
                "The points above are drawn from the cited sources listed in the references section."
            )
        if role == "critic":
            return (
                f"Critic review (det:{digest}): claims are traceable to listed sources; "
                "no unsupported numeric figures detected; recommend keeping citations inline."
            )
        # single-agent baseline / generic
        body = " ".join(f"{b}." for b in bullets[:5])
        return f"Answer (det:{digest}): {body}".strip()

    @staticmethod
    def _key_lines(text: str) -> list[str]:
        lines = [re.sub(r"\s+", " ", ln).strip(" -*\t") for ln in text.splitlines()]
        lines = [ln for ln in lines if len(ln) > 12]
        seen: set[str] = set()
        out: list[str] = []
        for ln in lines:
            key = ln.lower()
            if key not in seen:
                seen.add(key)
                out.append(ln)
        return out[:6] or ["No substantial input was provided."]

    # ---------------------------------------------------------------- openai
    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=8))
    def _openai_complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Real provider call. Returns LLMResponse with exact usage from the API."""

        from openai import OpenAI  # imported lazily so offline runs need no SDK

        client = OpenAI(api_key=self.settings.openai_api_key)
        api_resp = client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0.2,
            timeout=self.settings.timeout_seconds,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = api_resp.choices[0].message.content or ""
        usage = api_resp.usage
        input_tokens = usage.prompt_tokens if usage else _approx_tokens(system_prompt + user_prompt)
        output_tokens = usage.completion_tokens if usage else _approx_tokens(content)
        cost = (
            input_tokens / 1000 * self.settings.price_per_1k_input
            + output_tokens / 1000 * self.settings.price_per_1k_output
        )
        return LLMResponse(content=content, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A — naive baseline.

    - Within-session (per-thread) memory only.
    - No persistent `User.md`.
    - Forgets long-term facts whenever a new thread starts.
    - Naively re-processes the whole thread history every turn, so prompt cost
      grows quadratically on long threads.
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        if self.langchain_agent is not None:
            try:
                return self._reply_live(thread_id, message)
            except Exception:
                # Network / provider failure -> stay deterministic.
                pass
        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).token_usage

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).prompt_tokens_processed

    def compaction_count(self, thread_id: str) -> int:
        # Baseline has no compact memory.
        return 0

    # -- internals ---------------------------------------------------------

    def _session(self, thread_id: str) -> SessionState:
        return self.sessions.setdefault(thread_id, SessionState())

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        session = self._session(thread_id)
        session.messages.append({"role": "user", "content": message})

        # Naive baseline carries the full thread history every single turn.
        history_tokens = sum(estimate_tokens(m["content"]) for m in session.messages)
        session.prompt_tokens_processed += history_tokens

        response = self._offline_response(session, message)

        session.messages.append({"role": "assistant", "content": response})
        session.token_usage += estimate_tokens(response)
        return {
            "response": response,
            "token_usage": session.token_usage,
            "prompt_tokens_processed": session.prompt_tokens_processed,
            "compactions": 0,
        }

    def _offline_response(self, session: SessionState, message: str) -> str:
        """Deterministic reply using ONLY the current thread.

        With no long-term memory, a recall question asked in a fresh thread
        cannot be answered — which is exactly the behaviour we want to expose.
        """

        # Echo within-thread facts only; never recall across threads.
        prior_user = [m["content"] for m in session.messages[:-1] if m["role"] == "user"]
        if message.strip().endswith("?"):
            if not prior_user:
                return "Trong phiên này mình chưa có đủ thông tin để trả lời câu hỏi đó."
            return "Dựa trên phiên hiện tại, mình chỉ biết những gì bạn vừa nói trong thread này."
        return "Mình đã ghi nhận trong phiên này (baseline không nhớ qua phiên mới)."

    def _reply_live(self, thread_id: str, message: str) -> dict[str, Any]:
        session = self._session(thread_id)
        session.messages.append({"role": "user", "content": message})

        history_tokens = sum(estimate_tokens(m["content"]) for m in session.messages)
        session.prompt_tokens_processed += history_tokens

        # Send only the current thread history (no persistent memory).
        result = self.langchain_agent.invoke(session.messages)
        response = getattr(result, "content", str(result))

        session.messages.append({"role": "assistant", "content": response})
        session.token_usage += estimate_tokens(response)
        return {
            "response": response,
            "token_usage": session.token_usage,
            "prompt_tokens_processed": session.prompt_tokens_processed,
            "compactions": 0,
        }

    def _maybe_build_langchain_agent(self):
        """Build a real chat model only when explicitly enabled.

        Offline-deterministic by default so tests and benchmarks reproduce.
        Set `LIVE_AGENT=1` to call the real provider configured in `.env`.
        """

        if self.force_offline or os.getenv("LIVE_AGENT", "0") != "1":
            return None
        try:
            return build_chat_model(self.config.model)
        except Exception:
            return None

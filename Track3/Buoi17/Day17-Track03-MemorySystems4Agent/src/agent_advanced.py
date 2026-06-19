from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import (
    CompactMemoryManager,
    UserProfileStore,
    estimate_tokens,
    extract_profile_updates,
)
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


# Order in which facts are rendered into a recall answer.
_ANSWER_FIELDS = [
    ("name", "tên"),
    ("location", "nơi ở hiện tại"),
    ("profession", "nghề nghiệp"),
    ("response_style", "style trả lời"),
    ("drink", "đồ uống"),
    ("food", "món ăn"),
    ("pet", "thú cưng"),
    ("interests", "quan tâm"),
]


class AdvancedAgent:
    """Agent B — advanced agent with three memory layers.

    1. within-session memory (recent turns, via compact memory)
    2. persistent `User.md` (cross-session facts, newest correction wins)
    3. compact memory (summarises old turns once a thread grows too long)
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}
        self.langchain_agent = self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        if self.langchain_agent is not None:
            try:
                return self._reply_live(user_id, thread_id, message)
            except Exception:
                pass
        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    # -- internals ---------------------------------------------------------

    # Cumulative facts accumulate over turns; the rest are latest-correction-wins.
    _MERGE_KEYS = {"response_style", "interests"}

    def _ingest(self, user_id: str, message: str) -> None:
        """Persist any confidently extracted facts into `User.md`.

        - Single-valued facts (location, profession, ...): newest value wins.
        - Multi-valued facts (response_style, interests): merge with existing
          so a later partial mention does not erase earlier preferences.
        """

        updates = extract_profile_updates(message)
        if not updates:
            return
        existing = self.profile_store.facts(user_id)
        for key, value in updates.items():
            if key in self._MERGE_KEYS and existing.get(key):
                old_parts = [p.strip() for p in existing[key].split(",") if p.strip()]
                new_parts = [p.strip() for p in value.split(",") if p.strip()]
                merged = list(dict.fromkeys(old_parts + new_parts))
                value = ", ".join(merged)
            self.profile_store.upsert_fact(user_id, key, value)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        # 1-2. extract stable facts and persist them (conflict-aware).
        self._ingest(user_id, message)
        # 3. append into compact short-term memory (may trigger compaction).
        self.compact_memory.append(thread_id, "user", message)
        # 4. estimate how much context this turn actually carried.
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(
            thread_id, 0
        ) + self._estimate_prompt_context_tokens(user_id, thread_id)
        # 5. answer from persisted memory.
        response = self._offline_response(user_id, thread_id, message)
        # 6. record assistant turn + token accounting.
        self.compact_memory.append(thread_id, "assistant", response)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + estimate_tokens(response)
        return {
            "response": response,
            "token_usage": self.thread_tokens[thread_id],
            "prompt_tokens_processed": self.thread_prompt_tokens[thread_id],
            "compactions": self.compaction_count(thread_id),
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Context carried into one turn = User.md + summary + recent messages.

        Unlike the baseline (which re-sends the whole history), this stays
        bounded once compaction kicks in.
        """

        ctx = self.compact_memory.context(thread_id)
        total = estimate_tokens(self.profile_store.read_text(user_id))
        total += estimate_tokens(str(ctx.get("summary", "")))
        for m in ctx.get("messages", []):  # type: ignore[union-attr]
            total += estimate_tokens(m.get("content", ""))
        return total

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Answer from persisted memory so cross-session recall works."""

        facts = self.profile_store.facts(user_id)
        if not facts:
            return "Mình chưa nhớ được thông tin nào về bạn."

        parts = [f"{label}: {facts[key]}" for key, label in _ANSWER_FIELDS if key in facts]
        return "Theo hồ sơ mình nhớ — " + "; ".join(parts) + "."

    def _reply_live(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        self._ingest(user_id, message)
        self.compact_memory.append(thread_id, "user", message)
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(
            thread_id, 0
        ) + self._estimate_prompt_context_tokens(user_id, thread_id)

        ctx = self.compact_memory.context(thread_id)
        system = (
            "Bạn là trợ lý có trí nhớ dài hạn. Hồ sơ người dùng:\n"
            + self.profile_store.read_text(user_id)
            + "\n\n"
            + str(ctx.get("summary", ""))
        )
        recent = [HumanMessage(content=m["content"]) for m in ctx.get("messages", []) if m["role"] == "user"]  # type: ignore[index]
        result = self.langchain_agent.invoke([SystemMessage(content=system), *recent])
        response = getattr(result, "content", str(result))

        self.compact_memory.append(thread_id, "assistant", response)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + estimate_tokens(response)
        return {
            "response": response,
            "token_usage": self.thread_tokens[thread_id],
            "prompt_tokens_processed": self.thread_prompt_tokens[thread_id],
            "compactions": self.compaction_count(thread_id),
        }

    def _maybe_build_langchain_agent(self):
        """Build a real chat model only when `LIVE_AGENT=1` (offline by default)."""

        if self.force_offline or os.getenv("LIVE_AGENT", "0") != "1":
            return None
        try:
            return build_chat_model(self.config.model)
        except Exception:
            return None

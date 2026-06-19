from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Heuristic token estimator (good enough for offline benchmarking).

    Approximates ~4 characters per token. Returns 0 for empty text.
    """

    stripped = (text or "").strip()
    if not stripped:
        return 0
    return max(1, round(len(stripped) / 4))


# ---------------------------------------------------------------------------
# Persistent user profile (User.md)
# ---------------------------------------------------------------------------

_PROFILE_HEADER = "# User Profile\n\n## Facts\n"
# Human-friendly labels for known fact keys, used when rendering User.md.
_FACT_LABELS = {
    "name": "name",
    "location": "location",
    "profession": "profession",
    "response_style": "response_style",
    "drink": "drink",
    "food": "food",
    "pet": "pet",
    "interests": "interests",
}


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`, one markdown file per user id.

    Facts are stored as ``- key: value`` lines under a ``## Facts`` section so
    they can be parsed back and upserted (newest correction wins).
    """

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        slug = re.sub(r"[^a-z0-9_-]+", "-", (user_id or "user").lower()).strip("-")
        slug = slug or "user"
        return self.root_dir / f"{slug}.md"

    def read_text(self, user_id: str) -> str:
        path = self.path_for(user_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return _PROFILE_HEADER

    def write_text(self, user_id: str, content: str) -> Path:
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        text = self.read_text(user_id)
        if search_text not in text:
            return False
        self.write_text(user_id, text.replace(search_text, replacement, 1))
        return True

    def file_size(self, user_id: str) -> int:
        path = self.path_for(user_id)
        return path.stat().st_size if path.exists() else 0

    # -- structured fact helpers -------------------------------------------

    def facts(self, user_id: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        for line in self.read_text(user_id).splitlines():
            m = re.match(r"^-\s*([A-Za-z_]+):\s*(.+)$", line.strip())
            if m:
                facts[m.group(1)] = m.group(2).strip()
        return facts

    def _render(self, facts: dict[str, str]) -> str:
        lines = [_PROFILE_HEADER.rstrip("\n")]
        for key, value in facts.items():
            label = _FACT_LABELS.get(key, key)
            lines.append(f"- {label}: {value}")
        return "\n".join(lines) + "\n"

    def upsert_fact(self, user_id: str, key: str, value: str) -> None:
        """Insert or overwrite a single fact (latest correction wins)."""

        value = (value or "").strip()
        if not value:
            return
        facts = self.facts(user_id)
        facts[key] = value
        self.write_text(user_id, self._render(facts))


# ---------------------------------------------------------------------------
# Fact extraction from raw Vietnamese user messages
# ---------------------------------------------------------------------------

_KNOWN_CITIES = ["Đà Nẵng", "Hà Nội", "Huế", "Hồ Chí Minh", "Sài Gòn", "Hội An"]
_KNOWN_PROFESSIONS = [
    "MLOps engineer",
    "backend engineer",
    "data engineer",
    "ML engineer",
    "product manager",
]
# Markers that flip an assertion (so we ignore the corrected-away value).
_NEGATIONS = ["không còn", "không phải", "đừng", "chứ không", "thay vì", "không đổi"]
# Joke / hypothetical markers: skip profession/location updates for that turn.
_JOKE_MARKERS = ["đùa", "câu đùa"]


def _is_negated(message: str, idx: int, window: int = 22) -> bool:
    before = message[max(0, idx - window): idx].lower()
    return any(neg in before for neg in _NEGATIONS)


def _last_positive(message: str, candidates: list[str], trigger: str | None) -> str | None:
    """Return the last non-negated candidate phrase asserted in the message.

    If ``trigger`` is given (e.g. "ở "), only matches preceded by it count, so
    "nhắc Huế" is ignored while "ở Huế" is accepted.
    """

    best: tuple[int, str] | None = None
    for phrase in candidates:
        pattern = re.escape(phrase)
        if trigger:
            pattern = re.escape(trigger) + r"\s*" + pattern
        for m in re.finditer(pattern, message):
            phrase_idx = m.end() - len(phrase)
            if _is_negated(message, m.start()):
                continue
            if best is None or phrase_idx > best[0]:
                best = (phrase_idx, phrase)
    return best[1] if best else None


def extract_profile_updates(message: str) -> dict[str, str]:
    """Convert raw user text into stable profile facts.

    Guardrails (bonus: conflict / noise handling):
    - Skip question turns (they ask, they do not assert).
    - Skip joke / hypothetical turns for profession & location.
    - Honour corrections: a negated value ("không còn ... backend") is dropped,
      and the latest positively asserted value wins.
    """

    if not message:
        return {}
    msg = message.strip()
    # Question turns ask for facts, they do not provide them.
    if msg.endswith("?"):
        return {}

    low = msg.lower()
    updates: dict[str, str] = {}
    is_joke = any(j in low for j in _JOKE_MARKERS)

    # name: "mình tên là X" / "tên mình là X"
    name_m = re.search(r"tên\s+(?:mình\s+)?là\s+([^.,!?\n]+)", msg)
    if name_m:
        name = name_m.group(1).strip()
        if name and name.lower() not in {"gì", "gì?", "gì."} and len(name) <= 40:
            updates["name"] = name

    # location: only "ở <city>" or "nơi ở ... <city>" count as assertions.
    if not is_joke:
        loc = _last_positive(msg, _KNOWN_CITIES, trigger="ở")
        if loc is None:
            nm = re.search(
                r"nơi ở(?:\s+hiện tại)?(?:\s+là)?\s+(" + "|".join(map(re.escape, _KNOWN_CITIES)) + r")",
                msg,
            )
            if nm:
                loc = nm.group(1)
        if loc:
            updates["location"] = loc

    # profession: latest non-negated, skip joke turns.
    if not is_joke:
        prof = _last_positive(msg, _KNOWN_PROFESSIONS, trigger=None)
        if prof:
            updates["profession"] = prof

    # response style
    style_parts: list[str] = []
    if "ngắn gọn" in low:
        style_parts.append("ngắn gọn")
    if "3 bullet" in low:
        style_parts.append("3 bullet")
    elif "bullet" in low:
        style_parts.append("bullet")
    if "ví dụ thực chiến" in low:
        style_parts.append("có ví dụ thực chiến")
    elif "ví dụ thực tế" in low:
        style_parts.append("có ví dụ thực tế")
    if style_parts:
        updates["response_style"] = ", ".join(dict.fromkeys(style_parts))

    # simple whitelist preferences
    if "cà phê sữa đá" in low:
        updates["drink"] = "cà phê sữa đá"
    if "mì quảng" in low:
        updates["food"] = "mì Quảng"
    if "corgi" in low:
        updates["pet"] = "corgi tên Bơ" if "bơ" in low else "corgi"

    # technical interests
    interests: list[str] = []
    if "python" in low:
        interests.append("Python")
    if re.search(r"\bAI\b", msg):
        interests.append("AI ứng dụng")
    if interests:
        updates["interests"] = ", ".join(interests)

    return updates


# ---------------------------------------------------------------------------
# Compact memory for long threads
# ---------------------------------------------------------------------------

def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact heuristic summary of older messages.

    Keeps only the most recent ``max_items`` of the older block and truncates
    each so the summary is meaningfully smaller than the original text.
    """

    if not messages:
        return ""
    recent = messages[-max_items:]
    bullets = []
    for m in recent:
        content = " ".join((m.get("content") or "").split())
        if len(content) > 90:
            content = content[:90].rstrip() + "…"
        bullets.append(f"- {m.get('role', 'user')}: {content}")
    return "Tóm tắt hội thoại cũ:\n" + "\n".join(bullets)


@dataclass
class CompactMemoryManager:
    """Compact memory: keep recent messages in full, compress the rest.

    Per-thread state holds ``messages`` (recent, full), a running ``summary``
    of older turns, and a ``compactions`` counter for benchmarking.
    """

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def _thread(self, thread_id: str) -> dict[str, object]:
        return self.state.setdefault(
            thread_id, {"messages": [], "summary": "", "compactions": 0}
        )

    def _tokens(self, thread: dict[str, object]) -> int:
        total = estimate_tokens(str(thread["summary"]))
        for m in thread["messages"]:  # type: ignore[union-attr]
            total += estimate_tokens(m.get("content", ""))
        return total

    def append(self, thread_id: str, role: str, content: str) -> None:
        thread = self._thread(thread_id)
        thread["messages"].append({"role": role, "content": content})  # type: ignore[union-attr]

        # Compact while we are over budget and still have something to compress.
        while (
            self._tokens(thread) > self.threshold_tokens
            and len(thread["messages"]) > self.keep_messages  # type: ignore[arg-type]
        ):
            messages = thread["messages"]  # type: ignore[assignment]
            older = messages[: len(messages) - self.keep_messages]
            kept = messages[len(messages) - self.keep_messages:]
            new_summary = summarize_messages(older)
            existing = str(thread["summary"])
            combined = (existing + "\n" + new_summary).strip() if existing else new_summary
            # Bound the running summary so compact context stays small.
            lines = [ln for ln in combined.splitlines() if ln.strip()]
            if len(lines) > 12:
                lines = ["Tóm tắt hội thoại cũ:"] + lines[-11:]
            thread["summary"] = "\n".join(lines)
            thread["messages"] = kept
            thread["compactions"] = int(thread["compactions"]) + 1  # type: ignore[arg-type]

    def context(self, thread_id: str) -> dict[str, object]:
        return self._thread(thread_id)

    def compaction_count(self, thread_id: str) -> int:
        return int(self._thread(thread_id)["compactions"])  # type: ignore[arg-type]

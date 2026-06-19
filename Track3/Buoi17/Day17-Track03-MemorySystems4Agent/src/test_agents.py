from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import CompactMemoryManager, UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Isolated config: state in tmp, low compact threshold for fast triggering."""

    provider = ProviderConfig(provider="custom", model_name="offline", temperature=0.0)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return LabConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=state_dir,
        compact_threshold_tokens=60,
        compact_keep_messages=2,
        model=provider,
        judge_model=provider,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    store = UserProfileStore(tmp_path / "profiles")

    # Default profile when nothing written yet.
    assert "User Profile" in store.read_text("u1")
    assert store.file_size("u1") == 0

    store.upsert_fact("u1", "name", "DũngCT")
    assert "DũngCT" in store.read_text("u1")
    assert store.file_size("u1") > 0

    # Edit replaces in place.
    assert store.edit_text("u1", "DũngCT", "DũngCT Updated") is True
    assert "DũngCT Updated" in store.read_text("u1")
    assert store.edit_text("u1", "not-there", "x") is False

    # Upsert overwrites a single fact (latest-wins).
    store.upsert_fact("u1", "location", "Đà Nẵng")
    store.upsert_fact("u1", "location", "Huế")
    facts = store.facts("u1")
    assert facts["location"] == "Huế"


def test_compact_trigger(tmp_path: Path) -> None:
    cm = CompactMemoryManager(threshold_tokens=60, keep_messages=2)
    long_msg = "Đây là một câu rất dài để ép compact memory kích hoạt nhiều lần. " * 3
    for i in range(8):
        cm.append("t1", "user", f"{i} {long_msg}")

    assert cm.compaction_count("t1") > 0
    ctx = cm.context("t1")
    # Recent messages are bounded by keep_messages.
    assert len(ctx["messages"]) <= 2
    # Older content was moved into the summary.
    assert "Tóm tắt" in str(ctx["summary"])


def test_cross_session_recall(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    advanced = AdvancedAgent(config=config, force_offline=True)
    baseline = BaselineAgent(config=config, force_offline=True)

    # Session 1: user states their name.
    advanced.reply("dung", "session-1", "Chào, mình tên là DũngCT.")
    baseline.reply("dung", "session-1", "Chào, mình tên là DũngCT.")

    # Session 2 (fresh thread): ask for the name.
    q = "Mình tên là gì?"
    adv_ans = advanced.reply("dung", "session-2", q)["response"]
    base_ans = baseline.reply("dung", "session-2", q)["response"]

    # Advanced remembers via User.md; baseline forgets across threads.
    assert "DũngCT" in adv_ans
    assert "DũngCT" not in base_ans


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    advanced = AdvancedAgent(config=config, force_offline=True)
    baseline = BaselineAgent(config=config, force_offline=True)

    long_turn = (
        "Mình kể một đoạn rất dài về công việc MLOps, tin tức và preference để "
        "ép ngữ cảnh phình ra nhằm stress test lớp compact memory của agent. "
    ) * 4

    thread = "long-thread"
    for i in range(12):
        advanced.reply("dung", thread, f"Lượt {i}: {long_turn}")
        baseline.reply("dung", thread, f"Lượt {i}: {long_turn}")

    adv_prompt = advanced.prompt_token_usage(thread)
    base_prompt = baseline.prompt_token_usage(thread)

    # Compaction must have happened, and it must keep the advanced prompt load
    # below the naive baseline that re-sends the whole history every turn.
    assert advanced.compaction_count(thread) > 0
    assert adv_prompt < base_prompt

"""Runtime cho Actor / Evaluator / Reflector.

Có HAI chế độ, chọn tự động:

1. LLM THẬT  — khi bật cờ môi trường (xem llm.py). Mỗi hàm gọi LLM thật,
   token & latency được đo thật và đẩy vào USAGE để agents.py đọc.

2. MÔ PHỎNG DETERMINISTIC (mock) — mặc định khi chưa có API key. Đây là
   extension `mock_mode_for_autograding`: thay vì hard-code 4 qid như scaffold
   gốc, ta sinh failure mode **data-driven theo hash(qid)** để mọi dataset đều
   tạo ra phổ lỗi thực tế (entity_drift, incomplete_multi_hop, wrong_final_answer,
   looping, reflection_overfit) và cho thấy Reflexion phục hồi tốt hơn ReAct.
"""
from __future__ import annotations
import hashlib
import json

from . import llm
import threading

from .prompts import ACTOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTOR_SYSTEM
from .schemas import JudgeResult, QAExample, ReflectionEntry
from .utils import normalize_answer

# ---- Theo dõi token/latency thật cho mỗi attempt -----------------------------
# Dùng thread-local để chạy SONG SONG (ThreadPoolExecutor) không bị đua dữ liệu:
# mỗi luồng có bộ đếm riêng.
_USAGE = threading.local()


def reset_usage() -> None:
    _USAGE.tokens = 0
    _USAGE.latency_ms = 0


def get_usage() -> dict:
    return {"tokens": getattr(_USAGE, "tokens", 0), "latency_ms": getattr(_USAGE, "latency_ms", 0)}


def _record(result: "llm.LLMResult") -> None:
    _USAGE.tokens = getattr(_USAGE, "tokens", 0) + result.total_tokens
    _USAGE.latency_ms = getattr(_USAGE, "latency_ms", 0) + result.latency_ms


# ---------------------------------------------------------------------------
# Lớp mô phỏng deterministic: gán "kịch bản lỗi" cho mỗi câu hỏi theo hash(qid)
# ---------------------------------------------------------------------------
RECOVERABLE_MODES = ["entity_drift", "incomplete_multi_hop", "wrong_final_answer"]
HARD_MODES = ["looping", "reflection_overfit"]

# Giữ tương thích ngược với scaffold gốc (test/đọc tay vẫn import được).
FAILURE_MODE_BY_QID = {"hp2": "incomplete_multi_hop", "hp4": "wrong_final_answer", "hp6": "entity_drift", "hp8": "entity_drift"}


def _hash(qid: str) -> int:
    return int(hashlib.md5(qid.encode("utf-8")).hexdigest(), 16)


def scenario(qid: str) -> dict:
    """Trả về kịch bản deterministic cho 1 câu hỏi.

    kind:
      - "ok"          : cả hai agent đúng ngay attempt 1 (~60%)
      - "recoverable" : ReAct sai; Reflexion phục hồi ở attempt sau (~25%)
      - "hard"        : cả hai sai; Reflexion mắc lỗi đặc thù (looping/overfit) (~15%)
    """
    # Các qid cũ của scaffold giữ hành vi gốc để không phá test/demo cũ.
    if qid in FAILURE_MODE_BY_QID:
        mode = FAILURE_MODE_BY_QID[qid]
        return {"kind": "recoverable", "react_mode": mode, "reflexion_mode": "none", "recover_attempt": 2}

    h = _hash(qid)
    r = h % 100
    if r < 60:
        return {"kind": "ok", "react_mode": "none", "reflexion_mode": "none", "recover_attempt": 1}
    if r < 85:
        react_mode = RECOVERABLE_MODES[h % len(RECOVERABLE_MODES)]
        recover_attempt = 2 if react_mode != "incomplete_multi_hop" else 3
        return {"kind": "recoverable", "react_mode": react_mode, "reflexion_mode": "none", "recover_attempt": recover_attempt}
    reflexion_mode = HARD_MODES[h % len(HARD_MODES)]
    return {"kind": "hard", "react_mode": "wrong_final_answer", "reflexion_mode": reflexion_mode, "recover_attempt": 999}


def final_failure_mode(qid: str, agent_type: str, is_correct: bool) -> str:
    """Failure mode cuối cùng cho RunRecord (dùng bởi agents.py ở chế độ mock)."""
    if is_correct:
        return "none"
    sc = scenario(qid)
    return sc["react_mode"] if agent_type == "react" else sc["reflexion_mode"]


def _wrong_answer(example: QAExample, mode: str) -> str:
    """Câu trả lời sai deterministic, có 'màu sắc' theo loại lỗi."""
    titles = [c.title for c in example.context]
    first_hop = titles[0] if titles else "unknown entity"
    if mode in ("entity_drift", "wrong_final_answer", "looping", "reflection_overfit"):
        return f"{first_hop}"  # dừng/nhảy sang thực thể của hop đầu
    if mode == "incomplete_multi_hop":
        return f"{first_hop}"  # chỉ trả lời được hop đầu, chưa hoàn tất hop sau
    return "not enough information"


# ---------------------------------------------------------------------------
# API chính: 3 hàm runtime
# ---------------------------------------------------------------------------
def actor_answer(example: QAExample, attempt_id: int, agent_type: str, reflection_memory: list[str]) -> str:
    if llm.llm_enabled():
        return _actor_llm(example, reflection_memory)

    sc = scenario(example.qid)
    if sc["kind"] == "ok":
        return example.gold_answer
    if agent_type == "react":
        return _wrong_answer(example, sc["react_mode"])
    # reflexion
    if attempt_id >= sc["recover_attempt"]:
        return example.gold_answer
    mode = sc["react_mode"] if sc["kind"] == "recoverable" else sc["reflexion_mode"]
    return _wrong_answer(example, mode)


def evaluator(example: QAExample, answer: str) -> JudgeResult:
    if llm.llm_enabled():
        return _evaluator_llm(example, answer)

    if normalize_answer(example.gold_answer) == normalize_answer(answer):
        return JudgeResult(score=1, reason="Final answer matches the gold answer after normalization.")
    return JudgeResult(
        score=0,
        reason="The answer did not complete every reasoning hop; it stopped at or drifted to an intermediate entity.",
        missing_evidence=["The final hop grounding the answer in the supporting paragraph is missing."],
        spurious_claims=[answer] if answer else [],
    )


def reflector(example: QAExample, attempt_id: int, judge: JudgeResult) -> ReflectionEntry:
    if llm.llm_enabled():
        return _reflector_llm(example, attempt_id, judge)

    return ReflectionEntry(
        attempt_id=attempt_id,
        failure_reason=judge.reason,
        lesson="A partial or first-hop answer is not enough; every hop must be completed and grounded in the context.",
        next_strategy="Re-read each supporting paragraph, chain the hops explicitly, then verify the final entity before answering.",
    )


# ---------------------------------------------------------------------------
# Triển khai LLM thật
# ---------------------------------------------------------------------------
def _format_context(example: QAExample) -> str:
    return "\n".join(f"[{c.title}] {c.text}" for c in example.context)


_ANSWER_PREFIXES = ("the answer is", "answer:", "final answer:", "answer is")


def _clean_answer(text: str) -> str:
    """Gọt câu trả lời actor về dạng ngắn gọn (tốt cho chấm exact-match):
    bỏ tiền tố lan man, dấu nháy bao quanh, dấu chấm cuối, lấy dòng đầu."""
    text = (text or "").strip()
    if not text:
        return ""
    text = text.splitlines()[0].strip()  # chỉ giữ dòng đầu
    low = text.lower()
    for p in _ANSWER_PREFIXES:
        if low.startswith(p):
            text = text[len(p):].strip()
            break
    text = text.strip().strip('"\'').strip()
    if text.endswith(".") and text.count(".") == 1:
        text = text[:-1].strip()
    return text


def _actor_llm(example: QAExample, reflection_memory: list[str]) -> str:
    memo = ""
    if reflection_memory:
        memo = "\n\nLessons from previous attempts:\n" + "\n".join(f"- {m}" for m in reflection_memory)
    user = f"Question: {example.question}\n\nContext:\n{_format_context(example)}{memo}\n\nAnswer concisely with only the final answer (a short phrase, name, or yes/no)."
    try:
        res = llm.chat(ACTOR_SYSTEM, user, temperature=0.0)
    except RuntimeError:
        return ""  # call chết hẳn -> coi như trả lời rỗng (sẽ bị chấm sai), không sập run
    _record(res)
    return _clean_answer(res.text)


def _evaluator_llm(example: QAExample, answer: str) -> JudgeResult:
    user = (
        f"Question: {example.question}\n"
        f"Gold answer: {example.gold_answer}\n"
        f"Predicted answer: {answer}\n\n"
        'Return JSON: {"score": 0 or 1, "reason": "...", '
        '"missing_evidence": [...], "spurious_claims": [...]}'
    )
    try:
        res = llm.chat(EVALUATOR_SYSTEM, user, temperature=0.0, json_mode=True)
    except RuntimeError:  # fallback exact-match nếu judge không gọi được
        ok = normalize_answer(example.gold_answer) == normalize_answer(answer)
        return JudgeResult(score=1 if ok else 0, reason="Fallback exact-match grading (judge call failed).")
    _record(res)
    try:
        data = json.loads(res.text)
        return JudgeResult(
            score=1 if int(data.get("score", 0)) == 1 else 0,
            reason=str(data.get("reason", "")),
            missing_evidence=list(data.get("missing_evidence", []) or []),
            spurious_claims=list(data.get("spurious_claims", []) or []),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback an toàn: chấm bằng exact match nếu LLM trả JSON hỏng.
        ok = normalize_answer(example.gold_answer) == normalize_answer(answer)
        return JudgeResult(score=1 if ok else 0, reason="Fallback exact-match grading (judge JSON unparseable).")


def _reflector_llm(example: QAExample, attempt_id: int, judge: JudgeResult) -> ReflectionEntry:
    user = (
        f"Question: {example.question}\n"
        f"Why the last answer was wrong: {judge.reason}\n"
        f"Missing evidence: {judge.missing_evidence}\n\n"
        'Return JSON: {"failure_reason": "...", "lesson": "...", "next_strategy": "..."}'
    )
    try:
        res = llm.chat(REFLECTOR_SYSTEM, user, temperature=0.2, json_mode=True)
    except RuntimeError:
        return ReflectionEntry(attempt_id=attempt_id, failure_reason=judge.reason, lesson="Complete every reasoning hop and ground the answer in the context.", next_strategy="Re-read the supporting paragraphs and verify the final entity before answering.")
    _record(res)
    try:
        data = json.loads(res.text)
        return ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=str(data.get("failure_reason", judge.reason)),
            lesson=str(data.get("lesson", "")),
            next_strategy=str(data.get("next_strategy", "")),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=judge.reason,
            lesson="Complete every reasoning hop and ground the final answer in the context.",
            next_strategy="Re-read the supporting paragraphs and verify the final entity before answering.",
        )

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from . import llm
from .mock_runtime import actor_answer, evaluator, final_failure_mode, get_usage, reflector, reset_usage
from .schemas import AttemptTrace, JudgeResult, QAExample, ReflectionEntry, RunRecord
from .utils import normalize_answer


def _estimate_tokens(attempt_id: int, agent_type: str) -> int:
    return 320 + (attempt_id * 65) + (120 if agent_type == "reflexion" else 0)


def _estimate_latency(attempt_id: int, agent_type: str) -> int:
    return 160 + (attempt_id * 40) + (90 if agent_type == "reflexion" else 0)


def _classify_failure_llm(judge: JudgeResult, traces: list[AttemptTrace], agent_type: str, max_attempts: int) -> str:
    """Phân loại failure mode từ phán đoán THẬT của evaluator (chế độ LLM).

    Khác với mock (dùng hash), ở đây mode phản ánh hành vi thật của agent:
    - reflexion dùng hết lượt mà vẫn sai: lặp lại đáp án -> looping; cứ đổi đáp án
      mà không hội tụ -> reflection_overfit.
    - còn lại: dựa vào tín hiệu của judge (spurious_claims / missing_evidence).
    """
    answers = [normalize_answer(t.answer) for t in traces]
    if agent_type == "reflexion" and len(traces) >= max_attempts:
        if len(set(answers)) < len(answers):
            return "looping"  # quay vòng trên cùng (vài) đáp án
        return "reflection_overfit"  # liên tục đổi đáp án, over-correct
    if judge.spurious_claims:
        return "entity_drift"
    if judge.missing_evidence:
        return "incomplete_multi_hop"
    return "wrong_final_answer"


@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    max_attempts: int = 1
    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_score = 0
        for attempt_id in range(1, self.max_attempts + 1):
            reset_usage()  # đo token/latency thật cho riêng attempt này
            answer = actor_answer(example, attempt_id, self.agent_type, reflection_memory)
            judge = evaluator(example, answer)
            final_answer = answer
            final_score = judge.score

            reflection: ReflectionEntry | None = None
            # Reflexion: nếu sai và còn lượt, phản chiếu rồi nạp bài học vào memory cho lần sau.
            if judge.score == 0 and self.agent_type == "reflexion" and attempt_id < self.max_attempts:
                reflection = reflector(example, attempt_id, judge)
                reflections.append(reflection)
                reflection_memory.append(reflection.next_strategy)

            # Token/latency: dùng số đo thật khi chạy LLM, ngược lại dùng ước lượng.
            if llm.llm_enabled():
                usage = get_usage()
                token_estimate = usage["tokens"]
                latency_ms = usage["latency_ms"]
            else:
                token_estimate = _estimate_tokens(attempt_id, self.agent_type)
                latency_ms = _estimate_latency(attempt_id, self.agent_type)

            traces.append(AttemptTrace(attempt_id=attempt_id, answer=answer, score=judge.score, reason=judge.reason, reflection=reflection, token_estimate=token_estimate, latency_ms=latency_ms))
            if judge.score == 1:
                break

        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        if not final_score and llm.llm_enabled():
            failure_mode = _classify_failure_llm(judge, traces, self.agent_type, self.max_attempts)
        else:
            failure_mode = final_failure_mode(example.qid, self.agent_type, bool(final_score))
        return RunRecord(qid=example.qid, question=example.question, gold_answer=example.gold_answer, agent_type=self.agent_type, predicted_answer=final_answer, is_correct=bool(final_score), attempts=len(traces), token_estimate=total_tokens, latency_ms=total_latency, failure_mode=failure_mode, reflections=reflections, traces=traces)

class ReActAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_type="react", max_attempts=1)

class ReflexionAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3) -> None:
        super().__init__(agent_type="reflexion", max_attempts=max_attempts)


def _failure_mode(qid: str, agent_type: str, max_attempts: int, judge: JudgeResult, traces: list[AttemptTrace], correct: bool) -> str:
    if not correct and llm.llm_enabled():
        return _classify_failure_llm(judge, traces, agent_type, max_attempts)
    return final_failure_mode(qid, agent_type, correct)


def run_pair(example: QAExample, max_attempts: int = 3) -> tuple[RunRecord, RunRecord]:
    """Chạy MỘT vòng Reflexion và suy ra cả ReAct lẫn Reflexion record.

    Tối ưu chi phí: ReAct == attempt-1 của Reflexion (cùng actor, chưa có memory),
    nên không cần chạy ReAct riêng -> tiết kiệm ~một nửa số call ở attempt 1.
    """
    reflection_memory: list[str] = []
    reflections: list[ReflectionEntry] = []
    traces: list[AttemptTrace] = []
    first_judge: JudgeResult | None = None
    judge: JudgeResult | None = None
    for attempt_id in range(1, max_attempts + 1):
        reset_usage()
        answer = actor_answer(example, attempt_id, "reflexion", reflection_memory)
        judge = evaluator(example, answer)
        if first_judge is None:
            first_judge = judge

        reflection: ReflectionEntry | None = None
        if judge.score == 0 and attempt_id < max_attempts:
            reflection = reflector(example, attempt_id, judge)
            reflections.append(reflection)
            reflection_memory.append(reflection.next_strategy)

        if llm.llm_enabled():
            usage = get_usage()
            token_estimate, latency_ms = usage["tokens"], usage["latency_ms"]
        else:
            token_estimate = _estimate_tokens(attempt_id, "reflexion")
            latency_ms = _estimate_latency(attempt_id, "reflexion")

        traces.append(AttemptTrace(attempt_id=attempt_id, answer=answer, score=judge.score, reason=judge.reason, reflection=reflection, token_estimate=token_estimate, latency_ms=latency_ms))
        if judge.score == 1:
            break

    t0 = traces[0]
    react_correct = bool(t0.score)
    react_record = RunRecord(
        qid=example.qid, question=example.question, gold_answer=example.gold_answer,
        agent_type="react", predicted_answer=t0.answer, is_correct=react_correct, attempts=1,
        token_estimate=t0.token_estimate, latency_ms=t0.latency_ms,
        failure_mode=_failure_mode(example.qid, "react", 1, first_judge, [t0], react_correct),
        reflections=[], traces=[t0],
    )

    refl_correct = bool(traces[-1].score)
    reflexion_record = RunRecord(
        qid=example.qid, question=example.question, gold_answer=example.gold_answer,
        agent_type="reflexion", predicted_answer=traces[-1].answer, is_correct=refl_correct, attempts=len(traces),
        token_estimate=sum(t.token_estimate for t in traces), latency_ms=sum(t.latency_ms for t in traces),
        failure_mode=_failure_mode(example.qid, "reflexion", max_attempts, judge, traces, refl_correct),
        reflections=reflections, traces=traces,
    )
    return react_record, reflexion_record

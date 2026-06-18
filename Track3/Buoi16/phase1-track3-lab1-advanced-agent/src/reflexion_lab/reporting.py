from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from .schemas import ReportPayload, RunRecord

def summarize(records: list[RunRecord]) -> dict:
    grouped: dict[str, list[RunRecord]] = defaultdict(list)
    for record in records:
        grouped[record.agent_type].append(record)
    summary: dict[str, dict] = {}
    for agent_type, rows in grouped.items():
        summary[agent_type] = {"count": len(rows), "em": round(mean(1.0 if r.is_correct else 0.0 for r in rows), 4), "avg_attempts": round(mean(r.attempts for r in rows), 4), "avg_token_estimate": round(mean(r.token_estimate for r in rows), 2), "avg_latency_ms": round(mean(r.latency_ms for r in rows), 2)}
    if "react" in summary and "reflexion" in summary:
        summary["delta_reflexion_minus_react"] = {"em_abs": round(summary["reflexion"]["em"] - summary["react"]["em"], 4), "attempts_abs": round(summary["reflexion"]["avg_attempts"] - summary["react"]["avg_attempts"], 4), "tokens_abs": round(summary["reflexion"]["avg_token_estimate"] - summary["react"]["avg_token_estimate"], 2), "latency_abs": round(summary["reflexion"]["avg_latency_ms"] - summary["react"]["avg_latency_ms"], 2)}
    return summary

def failure_breakdown(records: list[RunRecord]) -> dict:
    """Key theo TỪNG failure mode, kèm số lượng tách theo agent.

    Cách này cho thấy mode nào Reflexion vẫn còn mắc (looping, reflection_overfit)
    so với mode nào ReAct gây ra rồi được Reflexion sửa (entity_drift, ...).
    """
    grouped: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        grouped[record.failure_mode][record.agent_type] += 1
    return {mode: dict(counter) for mode, counter in sorted(grouped.items())}

def _build_discussion(records: list[RunRecord], summary: dict, fb: dict) -> str:
    react = summary.get("react", {})
    reflexion = summary.get("reflexion", {})
    delta = summary.get("delta_reflexion_minus_react", {})
    react_em = react.get("em", 0.0)
    refl_em = reflexion.get("em", 0.0)
    remaining = sorted(m for m, c in fb.items() if m != "none" and c.get("reflexion", 0) > 0)
    fixed = sorted(m for m, c in fb.items() if m != "none" and c.get("react", 0) > 0 and c.get("reflexion", 0) == 0)
    return (
        f"Across {len(records)} runs, Reflexion lifted exact-match from {react_em:.2%} (ReAct) to "
        f"{refl_em:.2%} (delta {delta.get('em_abs', 0):+.4f}), at the cost of more attempts "
        f"({delta.get('attempts_abs', 0):+.2f}), more tokens ({delta.get('tokens_abs', 0):+.0f}) and "
        f"higher latency ({delta.get('latency_abs', 0):+.0f} ms). The reflection memory was most useful on "
        f"failure modes that ReAct produced but Reflexion recovered from: {', '.join(fixed) or 'none observed'}. "
        f"Failure modes that persisted even with reflection were: {', '.join(remaining) or 'none'} — "
        f"'looping' shows the agent repeating an unproductive trajectory while 'reflection_overfit' shows the "
        f"reflection over-correcting away from a near-correct answer. Net takeaway: Reflexion pays off when the "
        f"first error is a recoverable reasoning gap (an incomplete hop or an entity drift) that a concrete "
        f"next-attempt strategy can close, but it cannot rescue questions where the evaluator signal is weak or "
        f"the agent gets stuck in a loop, and the extra token/latency budget must be justified by the EM gain."
    )

def build_report(records: list[RunRecord], dataset_name: str, mode: str = "mock") -> ReportPayload:
    examples = [{"qid": r.qid, "agent_type": r.agent_type, "question": r.question, "gold_answer": r.gold_answer, "predicted_answer": r.predicted_answer, "is_correct": r.is_correct, "attempts": r.attempts, "failure_mode": r.failure_mode, "reflection_count": len(r.reflections)} for r in records]
    summary = summarize(records)
    fb = failure_breakdown(records)
    extensions = ["structured_evaluator", "reflection_memory", "benchmark_report_json", "mock_mode_for_autograding"]
    return ReportPayload(meta={"dataset": dataset_name, "mode": mode, "num_records": len(records), "agents": sorted({r.agent_type for r in records})}, summary=summary, failure_modes=fb, examples=examples, extensions=extensions, discussion=_build_discussion(records, summary, fb))

def save_report(report: ReportPayload, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
    s = report.summary
    react = s.get("react", {})
    reflexion = s.get("reflexion", {})
    delta = s.get("delta_reflexion_minus_react", {})
    ext_lines = "\n".join(f"- {item}" for item in report.extensions)
    md = f"""# Lab 16 Benchmark Report

## Metadata
- Dataset: {report.meta['dataset']}
- Mode: {report.meta['mode']}
- Records: {report.meta['num_records']}
- Agents: {', '.join(report.meta['agents'])}

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | {react.get('em', 0)} | {reflexion.get('em', 0)} | {delta.get('em_abs', 0)} |
| Avg attempts | {react.get('avg_attempts', 0)} | {reflexion.get('avg_attempts', 0)} | {delta.get('attempts_abs', 0)} |
| Avg token estimate | {react.get('avg_token_estimate', 0)} | {reflexion.get('avg_token_estimate', 0)} | {delta.get('tokens_abs', 0)} |
| Avg latency (ms) | {react.get('avg_latency_ms', 0)} | {reflexion.get('avg_latency_ms', 0)} | {delta.get('latency_abs', 0)} |

## Failure modes
```json
{json.dumps(report.failure_modes, indent=2)}
```

## Extensions implemented
{ext_lines}

## Discussion
{report.discussion}
"""
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path

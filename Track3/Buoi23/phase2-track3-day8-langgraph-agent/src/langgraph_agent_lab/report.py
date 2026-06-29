"""Report generation helper.

TODO(student): implement report rendering using MetricsReport data
and the template in reports/lab_report_template.md.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .metrics import MetricsReport

STUDENT_NAME = "Lương Quốc Dũng"
DIAGRAM_PATH = Path("docs/graph.mmd")


def render_report(metrics: MetricsReport) -> str:
    """Render a complete lab report (markdown) from metrics data."""
    lines: list[str] = []
    a = lines.append

    a("# Day 08 Lab Report — LangGraph Agentic Orchestration")
    a("")
    a(f"- **Student:** {STUDENT_NAME}")
    a(f"- **Date:** {date.today().isoformat()}")
    a("- **Repo/commit:** see git log")
    a("")
    a("> Auto-generated from `outputs/metrics.json` by `report.render_report()`.")
    a("")

    # 1. Summary -------------------------------------------------------
    a("## 1. Metrics summary")
    a("")
    a("| Metric | Value |")
    a("|---|---:|")
    a(f"| Total scenarios | {metrics.total_scenarios} |")
    a(f"| Success rate | {metrics.success_rate:.1%} |")
    a(f"| Avg nodes visited | {metrics.avg_nodes_visited:.2f} |")
    a(f"| Total retries | {metrics.total_retries} |")
    a(f"| Total interrupts (HITL) | {metrics.total_interrupts} |")
    a(f"| Resume success | {metrics.resume_success} |")
    a("")

    # 2. Per-scenario -------------------------------------------------
    a("## 2. Per-scenario results")
    a("")
    a("| Scenario | Expected | Actual | OK | Nodes | Retries | Interrupts | Appr req/obs |")
    a("|---|---|---|:---:|---:|---:|---:|:---:|")
    for m in metrics.scenario_metrics:
        ok = "✅" if m.success else "❌"
        appr = f"{m.approval_required}/{m.approval_observed}"
        a(
            f"| {m.scenario_id} | {m.expected_route} | {m.actual_route} | {ok} "
            f"| {m.nodes_visited} | {m.retry_count} | {m.interrupt_count} | {appr} |"
        )
    a("")

    # 3. Architecture -------------------------------------------------
    a("## 3. Architecture")
    a("")
    a(
        "StateGraph over a typed `AgentState` (TypedDict). Flow: "
        "`START → intake → classify → [route_after_classify]` then one of five branches "
        "(`simple/tool/missing_info/risky/error`). The `tool → evaluate` pair forms a "
        "bounded retry loop via `route_after_evaluate` (success→answer, needs_retry→retry) "
        "and `route_after_retry` (attempt<max→tool, else→dead_letter). Risky tickets pass "
        "through `risky_action → approval → [route_after_approval]` (HITL gate). Every "
        "branch converges on `finalize → END`."
    )
    a("")
    a("- **LLM nodes:** `classify_node` (structured output → Route enum) and `answer_node` "
      "(grounded generation). `evaluate_node` adds an optional LLM-as-judge quality score.")
    a("")
    if DIAGRAM_PATH.exists():
        a("Graph topology (exported via `graph.get_graph().draw_mermaid()`):")
        a("")
        a("```mermaid")
        a(DIAGRAM_PATH.read_text(encoding="utf-8").strip())
        a("```")
        a("")

    # 4. State schema -------------------------------------------------
    a("## 4. State schema")
    a("")
    a("| Field | Reducer | Why |")
    a("|---|---|---|")
    a("| messages / tool_results / errors / events | append (`operator.add`) | audit trail |")
    a("| route / risk_level / attempt | overwrite | current value only |")
    a("| evaluation_result | overwrite | drives the retry gate |")
    a("| pending_question / proposed_action | overwrite | latest clarification / action |")
    a("| approval | overwrite | latest HITL decision |")
    a("")

    # 5. Failure analysis --------------------------------------------
    a("## 5. Failure analysis")
    a("")
    a("1. **Transient tool failure → retry loop.** `tool_node` returns an `ERROR` result on "
      "early error-route attempts; `evaluate_node` flags `needs_retry`; `route_after_retry` "
      "is bounded by `max_attempts`, so it escalates to `dead_letter` instead of looping "
      "forever (see `S07_dead_letter`).")
    a("2. **Risky action without approval.** Side-effecting tickets cannot reach the tool "
      "until `approval_node` records a decision; a rejection diverts to `clarify` rather "
      "than executing the action.")
    a("")

    # 6. Persistence --------------------------------------------------
    a("## 6. Persistence / recovery evidence")
    a("")
    a("Each scenario runs under its own `thread_id` (`thread-<scenario_id>`). With the "
      "`sqlite` checkpointer, state is durably written (WAL mode), enabling "
      "`get_state_history()` replay and crash-resume across process restarts.")
    a("")
    a("`scripts/persistence_demo.py` proves this: it runs a scenario under a `SqliteSaver`, "
      "lists the 12-snapshot checkpoint history (time-travel), then **closes the connection "
      "and drops the graph** to simulate a crash, re-opens a fresh saver on the same file, "
      "and recovers the full state by `thread_id` — `RESUME_SUCCESS: True`. Full log: "
      "`outputs/persistence_evidence.txt`.")
    a("")

    # 7. Extensions ---------------------------------------------------
    a("## 7. Extension work")
    a("")
    a("- SQLite checkpointer (durable persistence + crash-resume).")
    a("- LLM-as-judge inside `evaluate_node`.")
    a("- Real HITL via `LANGGRAPH_INTERRUPT=true` + `interrupt()` in `approval_node`.")
    a("- Mermaid graph diagram via `graph.get_graph().draw_mermaid()`.")
    a("")

    # 8. Improvement plan --------------------------------------------
    a("## 8. Improvement plan")
    a("")
    a("Replace the mock `tool_node` with real, idempotent tool calls (with timeouts and "
      "circuit-breaking), add structured tracing/observability, and wire a real reviewer "
      "queue for the HITL approval step.")
    a("")
    return "\n".join(lines)


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")

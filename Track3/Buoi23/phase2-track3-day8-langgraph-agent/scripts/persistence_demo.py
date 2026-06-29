"""Persistence & recovery evidence (bonus).

Demonstrates that the SQLite checkpointer gives durable, resumable state:

1. Run a scenario under a unique thread_id with a SqliteSaver.
2. Print the checkpoint history (time-travel evidence via get_state_history()).
3. Simulate a crash: drop the graph + close the DB connection entirely.
4. Re-open a *fresh* SqliteSaver on the same file and rebuild the graph, then
   read the state back by thread_id — proving the run survived the "crash".

Run:  python scripts/persistence_demo.py
Writes evidence to outputs/persistence_evidence.txt
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Route, Scenario, initial_state

DB_PATH = "outputs/checkpoints_demo.sqlite"
THREAD_ID = "thread-persist-demo"


def main() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        # ── clean slate ──
        for ext in ("", "-wal", "-shm"):
            p = Path(DB_PATH + ext)
            if p.exists():
                p.unlink()

        run_config = {"configurable": {"thread_id": THREAD_ID}}
        scenario = Scenario(
            id="persist-demo",
            query="Timeout failure while processing request",
            expected_route=Route.ERROR,
            should_retry=True,
        )

        # ── phase 1: run with a SQLite checkpointer ──
        cp1 = build_checkpointer("sqlite", DB_PATH)
        graph1 = build_graph(checkpointer=cp1)
        final = graph1.invoke(initial_state(scenario), config=run_config)
        print("=== PHASE 1: run completed under SqliteSaver ===")
        print(f"thread_id      : {THREAD_ID}")
        print(f"final route    : {final['route']}")
        print(f"final answer   : {final['final_answer'][:80]}...")
        print(f"attempts       : {final['attempt']}")

        # ── time-travel evidence: full checkpoint history ──
        history = list(graph1.get_state_history(run_config))
        print(f"\n=== checkpoint history: {len(history)} snapshots (newest first) ===")
        for snap in history[:6]:
            nxt = snap.next or ("END",)
            print(f"  step={snap.metadata.get('step'):>3}  next={nxt}")

        # ── phase 2: simulate crash — destroy graph + close connection ──
        cp1.conn.close()
        del graph1, cp1
        print("\n=== PHASE 2: process 'crash' simulated (graph dropped, DB closed) ===")

        # ── phase 3: fresh saver on same file → state must still be there ──
        cp2 = build_checkpointer("sqlite", DB_PATH)
        graph2 = build_graph(checkpointer=cp2)
        recovered = graph2.get_state(run_config)
        print("=== PHASE 3: reopened SqliteSaver, recovered state by thread_id ===")
        print(f"recovered route : {recovered.values.get('route')}")
        print(f"recovered answer: {recovered.values.get('final_answer', '')[:80]}...")
        ok = recovered.values.get("route") == "error" and bool(recovered.values.get("final_answer"))
        print(f"\nRESUME_SUCCESS  : {ok}")
        cp2.conn.close()

    evidence = buf.getvalue()
    Path("outputs").mkdir(exist_ok=True)
    Path("outputs/persistence_evidence.txt").write_text(evidence, encoding="utf-8")
    print(evidence)
    print("Wrote outputs/persistence_evidence.txt")


if __name__ == "__main__":
    main()

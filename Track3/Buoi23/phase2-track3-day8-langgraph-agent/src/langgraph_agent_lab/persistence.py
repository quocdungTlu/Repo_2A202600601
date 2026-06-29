"""Checkpointer adapter.

Maps a config string to a LangGraph checkpointer. The SQLite saver gives us
durable, crash-resumable state: each run uses its own thread_id, and the graph
can be replayed or resumed after a process restart.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_SQLITE_PATH = "outputs/checkpoints.sqlite"


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer for the requested backend.

    - "none"     → no persistence
    - "memory"   → in-process MemorySaver (default; fast, non-durable)
    - "sqlite"   → durable SqliteSaver (WAL mode) at `database_url` or DEFAULT_SQLITE_PATH
    - "postgres" → durable PostgresSaver via `database_url`
    """
    if kind == "none":
        return None

    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()

    if kind == "sqlite":
        from langgraph.checkpoint.sqlite import SqliteSaver

        db_path = database_url or DEFAULT_SQLITE_PATH
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the connection can be reused across the run;
        # WAL improves concurrent read/write durability for crash-resume.
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return SqliteSaver(conn=conn)

    if kind == "postgres":
        if not database_url:
            raise ValueError("postgres checkpointer requires a database_url")
        from langgraph.checkpoint.postgres import PostgresSaver

        saver = PostgresSaver.from_conn_string(database_url)
        saver.setup()
        return saver

    raise ValueError(f"Unknown checkpointer kind: {kind}")


def verify_resume(thread_id: str, database_url: str | None = None) -> bool:
    """Prove crash-resume on a durable SQLite backend.

    Opens a BRAND-NEW connection + graph (as if the original process had crashed)
    and reads the state back by `thread_id`. Returns True when a terminal state is
    recovered (route present and an answer/question produced). No LLM call is made —
    we only read the persisted checkpoint.
    """
    from .graph import build_graph

    checkpointer = build_checkpointer("sqlite", database_url)
    try:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
        values = snapshot.values or {}
        has_route = bool(values.get("route"))
        has_answer = bool(values.get("final_answer") or values.get("pending_question"))
        return has_route and has_answer
    finally:
        conn = getattr(checkpointer, "conn", None)
        if conn is not None:
            conn.close()

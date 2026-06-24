"""Tracing hooks.

Provider-agnostic. The default backend logs spans to Python's standard logging system
so traces are visible with ``LOG_LEVEL=DEBUG``. Plug in LangSmith, Langfuse, or
OpenTelemetry by replacing/augmenting the ``_emit`` function below.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any

_log = logging.getLogger("multi_agent_research_lab.tracing")


def _emit(span: dict[str, Any]) -> None:
    """Emit a completed span. Replace this to integrate with an external provider."""

    _log.debug("SPAN %s", json.dumps(span, default=str))


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Minimal span context manager.

    Yields a mutable span dict so callers can attach extra attributes at any point.
    Emits the completed span on exit. Duration is always populated.

    Example::

        with trace_span("researcher", {"query": q}) as span:
            ... do work ...
            span["attributes"]["cost_usd"] = resp.cost_usd
    """

    started = perf_counter()
    span: dict[str, Any] = {
        "name": name,
        "attributes": dict(attributes or {}),
        "duration_seconds": None,
        "error": None,
    }
    try:
        yield span
    except Exception as exc:  # noqa: BLE001
        span["error"] = str(exc)
        raise
    finally:
        span["duration_seconds"] = round(perf_counter() - started, 4)
        _emit(span)

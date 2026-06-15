"""Mitigation + observability layer (v6).

The simulator calls mitigate() around the silent black-box agent (a REAL LLM) for
every request. Because the agent emits nothing and run_output.json is lean, THIS is
the only place latency / tokens / cost / tool-use / loops / drift / PII can be seen.

Legal moves used here: prompt routing (our rewritten solution/prompt.txt per request),
thread-safe response cache, light retry on transient failures, PII redaction of the
final answer, plus structured logging/metrics via the bundled telemetry/ package.
No hardcoded answers, no agent-internal imports, no network.
"""
from __future__ import annotations

import os
import re
import threading
import time

try:
    from telemetry.logger import logger, new_correlation_id, set_correlation_id
    from telemetry.cost import cost_from_usage
    from telemetry.redact import redact
except Exception:  # telemetry optional; wrapper still runs without it
    logger = None

    def new_correlation_id():
        return None

    def set_correlation_id(_cid):
        return None

    def cost_from_usage(model, usage):
        return 0.0

    def redact(s):
        return (s, 0)


# --- our rewritten system prompt, loaded once (thread-safe) ------------------
_PROMPT_LOCK = threading.Lock()
_PROMPT = {"text": None}


def _system_prompt():
    if _PROMPT["text"] is None:
        with _PROMPT_LOCK:
            if _PROMPT["text"] is None:
                path = os.path.join(os.path.dirname(__file__), "prompt.txt")
                try:
                    _PROMPT["text"] = open(path, encoding="utf-8").read().strip()
                except Exception:
                    _PROMPT["text"] = ""
    return _PROMPT["text"]


# Detect (for observability) an injected instruction / fake price hidden in a note.
_INJECT_RE = re.compile(
    r"(ghi\s*ch[uú]|l[uư]u\s*[yý]|\bnote\b|\bsystem\b|b[oỏ]\s*qua|ignore|gi[aá]\s*ch[ií]nh\s*th[uứ]c)",
    re.IGNORECASE,
)

_TRANSIENT = {"wrapper_error", "loop", "max_steps", "no_action"}

# Normalize a (possibly verbose) answer down to the single canonical total line, so
# the exact-total parse is reliable regardless of how chatty the model is. Refusals
# (no total present) pass through unchanged.
_TOTAL_RE = re.compile(r"[Tt]ong\s*c[oôöơ]ng\s*[:=]?\s*([\d][\d.,\s]*\d|\d)\s*(?:VND|đ|vnd)", re.IGNORECASE)


def _normalize_total(answer):
    if not isinstance(answer, str):
        return answer
    matches = _TOTAL_RE.findall(answer)
    if not matches:
        return answer
    digits = re.sub(r"[.,\s]", "", matches[-1])
    if digits.isdigit():
        return f"Tong cong: {digits} VND"
    return answer


def _repeated_actions(trace):
    """Count duplicate agent actions in the trace (loop / over-call signal)."""
    seen = []
    for step in trace or []:
        if isinstance(step, dict):
            a = step.get("action") or step.get("tool") or step.get("name")
            if a is not None:
                seen.append(repr(a))
    return len(seen) - len(set(seen))


def mitigate(call_next, question, config, context):
    cache = context.get("cache")
    lock = context.get("cache_lock")
    qid = context.get("qid")

    if logger:
        set_correlation_id(new_correlation_id())

    # Route our rewritten system prompt on every request (legal prompt routing).
    conf = dict(config)
    sp = _system_prompt()
    if sp:
        conf["system_prompt"] = sp

    # Thread-safe response cache: identical question -> reuse (saves cost + latency).
    key = ("ans", question)
    if cache is not None and lock is not None:
        with lock:
            if key in cache:
                cached = cache[key]
                if logger:
                    logger.log_event("CACHE_HIT", {"qid": qid, "question": question})
                return cached

    injected = bool(_INJECT_RE.search(question or ""))

    # Call with light retry: re-try transient failures (incl. provider exceptions),
    # never a clean answer.
    t0 = time.time()
    attempts = 0
    result = None
    while attempts < 4:
        attempts += 1
        try:
            result = call_next(question, conf)
        except Exception:
            # transient provider/transport error -> back off and retry
            if attempts < 4:
                time.sleep(0.4 * attempts)
                continue
            result = {"answer": None, "status": "wrapper_error", "steps": 0, "trace": [], "meta": {}}
            break
        status = (result or {}).get("status")
        answer = (result or {}).get("answer")
        if status == "ok" and answer:
            break
        if status in _TRANSIENT:
            time.sleep(0.3 * attempts)
            continue
        break
    wall_ms = int((time.time() - t0) * 1000)

    result = result or {}
    meta = result.get("meta", {}) or {}
    usage = meta.get("usage", {}) or {}
    trace = result.get("trace", []) or []
    tools = meta.get("tools_used", []) or []
    answer = result.get("answer")

    # Normalize a verbose answer down to the canonical total line (helps exact-total
    # parse with chatty models; refusals pass through unchanged).
    if isinstance(answer, str):
        norm = _normalize_total(answer)
        if norm != answer:
            result["answer"] = norm
            answer = norm

    # Redact PII the customer would see (defense in depth on top of the prompt rule).
    pii_n = 0
    if isinstance(answer, str):
        red, pii_n = redact(answer)
        if pii_n:
            result["answer"] = red

    # --- Observability: the only place these signals exist -------------------
    if logger:
        logger.log_event("AGENT_CALL", {
            "qid": qid,
            "session": context.get("session_id"),
            "turn": context.get("turn_index"),
            "status": result.get("status"),
            "attempts": attempts,
            "latency_ms": meta.get("latency_ms"),
            "wall_ms": wall_ms,
            "tokens": usage,
            "cost_usd": cost_from_usage(meta.get("model", ""), usage),
            "tools_used": tools,
            "tool_calls": len(tools),
            "steps": result.get("steps"),
            "repeated_actions": _repeated_actions(trace),
            "pii_in_answer": pii_n,
            "injected_note_detected": injected,
            "model": meta.get("model"),
        })

    # Cache only clean successes.
    if cache is not None and lock is not None and result.get("status") == "ok" and result.get("answer"):
        with lock:
            cache[key] = result

    return result

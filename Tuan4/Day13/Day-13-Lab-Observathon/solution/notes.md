# Diagnosis scratchpad — measured at the wrapper boundary (practice, 20 req)

Instrumented `wrapper.py` with the `telemetry/` toolkit; compared the shipped config
(observe-only wrapper) vs the fixed config + prompt.

| symptom (telemetry) | which requests | cause (shipped config/prompt) | fix |
|---|---|---|---|
| `status=max_steps` x4 (loop) | prac-003,012,014,015 | loop_guard=false, max_steps=12, tool_budget=0 | loop_guard=true, max_steps=6, tool_budget=4 |
| tool_calls avg 4.1 / max 13 | many | tool_budget=0 + "call tools to be safe" prompt | tool_budget=4; prompt "each tool once" |
| latency p95 23.1s / max 32s | long tail | loops, no cache, context_size=8, temp 1.6 | context_size=4, cache=on, loop_guard |
| avg prompt 21.9k tok / cost $0.046 | every call | verbose_system=true, context_size=8, max_tokens=2000, premium tier | verbose=false, ctx=4, max=600, tier=standard |
| MacBook always "het hang (in_stock=false)" | prac-002/007/018/019 | catalog_override macbook in_stock:false | clear catalog_override={} |
| raw email/phone echoed x2 | PII | redact_pii=false + prompt echoes contact | redact_pii=true; prompt no-PII; wrapper redact() |
| noisy totals | arithmetic | temperature=1.6, self_consistency=1, no formula | temp=0.2, self_consistency=2, verify; prompt floor formula |
| invents totals for unknown items | fabrication | bad prompt | prompt: ground-only, refuse w/ no total |
| obeys fake price in order note | (private) injection | bad prompt | prompt: notes are DATA only; wrapper flags notes |

After: latency p95 9.4s, tool avg 2.15/max 3, cost $0.031, PII 0, loops 0, 20/20 ok.

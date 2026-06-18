# Lab 16 Benchmark Report

## Metadata
- Dataset: golden.json
- Mode: llm
- Records: 40
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 1.0 | 1.0 | 0.0 |
| Avg attempts | 1 | 1 | 0 |
| Avg token estimate | 454.1 | 454.1 | 0.0 |
| Avg latency (ms) | 5088 | 5088 | 0 |

## Failure modes
```json
{
  "none": {
    "react": 20,
    "reflexion": 20
  }
}
```

## Extensions implemented
- structured_evaluator
- reflection_memory
- benchmark_report_json
- mock_mode_for_autograding

## Discussion
Across 40 runs, Reflexion lifted exact-match from 100.00% (ReAct) to 100.00% (delta +0.0000), at the cost of more attempts (+0.00), more tokens (+0) and higher latency (+0 ms). The reflection memory was most useful on failure modes that ReAct produced but Reflexion recovered from: none observed. Failure modes that persisted even with reflection were: none — 'looping' shows the agent repeating an unproductive trajectory while 'reflection_overfit' shows the reflection over-correcting away from a near-correct answer. Net takeaway: Reflexion pays off when the first error is a recoverable reasoning gap (an incomplete hop or an entity drift) that a concrete next-attempt strategy can close, but it cannot rescue questions where the evaluator signal is weak or the agent gets stuck in a loop, and the extra token/latency budget must be justified by the EM gain.

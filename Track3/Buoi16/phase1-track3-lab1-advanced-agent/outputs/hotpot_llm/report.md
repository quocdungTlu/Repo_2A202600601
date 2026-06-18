# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_dev60.json
- Mode: llm
- Records: 120
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.7667 | 0.9333 | 0.1666 |
| Avg attempts | 1 | 1.3333 | 0.3333 |
| Avg token estimate | 691.92 | 948.4 | 256.48 |
| Avg latency (ms) | 2222.53 | 3334.25 | 1111.72 |

## Failure modes
```json
{
  "entity_drift": {
    "react": 6
  },
  "incomplete_multi_hop": {
    "react": 1
  },
  "looping": {
    "reflexion": 4
  },
  "none": {
    "react": 46,
    "reflexion": 56
  },
  "wrong_final_answer": {
    "react": 7
  }
}
```

## Extensions implemented
- structured_evaluator
- reflection_memory
- benchmark_report_json
- mock_mode_for_autograding

## Discussion
Across 120 runs, Reflexion lifted exact-match from 76.67% (ReAct) to 93.33% (delta +0.1666), at the cost of more attempts (+0.33), more tokens (+256) and higher latency (+1112 ms). The reflection memory was most useful on failure modes that ReAct produced but Reflexion recovered from: entity_drift, incomplete_multi_hop, wrong_final_answer. Failure modes that persisted even with reflection were: looping — 'looping' shows the agent repeating an unproductive trajectory while 'reflection_overfit' shows the reflection over-correcting away from a near-correct answer. Net takeaway: Reflexion pays off when the first error is a recoverable reasoning gap (an incomplete hop or an entity drift) that a concrete next-attempt strategy can close, but it cannot rescue questions where the evaluator signal is weak or the agent gets stuck in a loop, and the extra token/latency budget must be justified by the EM gain.

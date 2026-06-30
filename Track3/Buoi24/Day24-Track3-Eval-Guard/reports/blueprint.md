# CI/CD Blueprint: RAG Eval + Guardrail Stack

**Sinh viên:** Lương Quốc Dũng (2A202600601)
**Ngày:** 2026-06-30

---

## Guard Stack Architecture

```
User Input
    │
    ▼ (~2–5ms P95)
[Presidio PII Scan]
    │ block if: VN_CCCD (12 số) / VN_PHONE (0[3-9]xxxxxxxx) / EMAIL detected
    │ action:   return 400 + "PII detected in query"
    ▼ (~300–800ms P95)
[NeMo Input Rail]
    │ block if: off-topic / jailbreak / prompt injection / PII request
    │ action:   return 503 + refuse message từ rails.co
    ▼
[RAG Pipeline (Day 18)]
    │ M1 Chunk → M2 HybridSearch (BM25+Dense) → M3 CrossEncoder Rerank → GPT-4o-mini
    │ timeout: 5s; fallback: "Không tìm thấy thông tin phù hợp."
    ▼ (~300–800ms P95)
[NeMo Output Rail]
    │ flag if:  PII in response / sensitive content
    │ action:   replace with safe redirect message
    ▼
User Response
```

---

## Guard Stack Pipeline

| Layer           | Tool          | Latency P95 | Failure Action               |
|-----------------|---------------|-------------|------------------------------|
| PII Detection   | Presidio      | <10ms       | Reject 400 + log             |
| Topic/Jailbreak | NeMo Input    | <800ms      | 503 + refuse reason          |
| RAG Pipeline    | Day 18        | <2000ms     | Fallback "Không tìm thấy."   |
| Output Check    | NeMo Output   | <800ms      | Block + replace safe message |

---

## Latency Budget

*(Đo từ Task 12 — measure_p95_latency() với 10 inputs adversarial)*

| Layer        | P50 (ms) | P95 (ms) | P99 (ms) | Budget  |
|--------------|----------|----------|----------|---------|
| Presidio PII | ~3ms     | ~8ms     | ~12ms    | <10ms   |
| NeMo Input   | ~350ms   | ~700ms   | ~900ms   | <800ms  |
| **Total**    | ~355ms   | ~710ms   | ~915ms   | <1000ms |

---

## CI Gates (phải pass trước khi merge to main)

- [ ] RAGAS faithfulness ≥ 0.75 (measured on 50q test set)
- [ ] Adversarial suite pass rate ≥ 90% (18/20)
- [ ] P95 total guard latency < 1000ms
- [ ] 0 `# TODO` còn lại trong `src/phase_*.py`
- [ ] `pytest tests/` 100% pass

---

## Monitoring (điền dựa trên kết quả thực tế)

- P95 latency Presidio thực tế: ~8ms
- P95 latency NeMo thực tế: ~700ms
- P95 latency Total thực tế: ~710ms
- Adversarial pass rate: ≥15/20
- Worst RAGAS metric: `context_recall`
- Dominant failure distribution: `multi_hop`

# Day 10 Reliability Final Report

## Metrics Summary

| Metric | Value |
|---|---:|
| total_requests | 300 |
| availability | 0.99 |
| error_rate | 0.01 |
| latency_p50_ms | 278.99 |
| latency_p95_ms | 314.56 |
| latency_p99_ms | 319.31 |
| fallback_success_rate | 0.9647 |
| cache_hit_rate | 0.5967 |
| circuit_open_count | 9 |
| recovery_time_ms | 2288.0537509918213 |
| estimated_cost | 0.049508 |
| estimated_cost_saved | 0.179 |

## Chaos Scenarios

| Scenario | Status |
|---|---|
| primary_timeout_100 | pass |
| primary_flaky_50 | pass |
| all_healthy | pass |

## Analysis TODO(student)

Explain what failed, why the fallback path worked or did not work, and what you would change before production.
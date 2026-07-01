# Day 10 Reliability Report

## 1. Architecture summary

```
User Request
     |
     v
[ReliabilityGateway]
     |
     +---> [ResponseCache.get(prompt)]
     |          |
     |     HIT? +---> return GatewayResponse(route="cache_hit:{score:.2f}", cache_hit=True, latency=0, cost=0)
     |
     | MISS
     v
[CircuitBreaker: primary]
     |  CLOSED/HALF_OPEN?
     +---> FakeLLMProvider("primary", fail_rate=0.25)
     |          |
     |     OK?  +---> cache.set() ---> return GatewayResponse(route="primary")
     |     FAIL? --> save error, continue
     |
     |  OPEN (before reset_timeout)?
     +---> CircuitOpenError, skip
     |
     v
[CircuitBreaker: backup]
     |  CLOSED/HALF_OPEN?
     +---> FakeLLMProvider("backup", fail_rate=0.05)
     |          |
     |     OK?  +---> cache.set() ---> return GatewayResponse(route="fallback")
     |     FAIL? --> save error, continue
     |
     v
[Static fallback]
     ---> return GatewayResponse(route="static_fallback", text="The service is temporarily degraded...")
```

**Implementation notes:**
- `ResponseCache`: in-memory, TTL eviction, n-gram cosine similarity, privacy guardrails, false-hit detection.
- `CircuitBreaker`: CLOSED → OPEN (after `failure_threshold` failures) → HALF_OPEN (after `reset_timeout_seconds`) → CLOSED (after `success_threshold` successes).
- `SharedRedisCache`: Redis-backed, shared across instances via `hset/expire`, same similarity logic as in-memory.
- `ReliabilityGateway`: cache-first, then iterates providers in order through their circuit breakers.

---

## 2. Configuration

| Setting | Value | Reason |
|---|---:|---|
| failure_threshold | 3 | Tolerate 2 transient failures before opening; prevents storm on single spike |
| reset_timeout_seconds | 2.0 | Short timeout lets system recover quickly; verified ~2.3s recovery in chaos runs |
| success_threshold | 1 | Single probe success closes the circuit (fast recovery, low probe overhead) |
| cache TTL | 300 s | Long enough for repeated FAQ queries within a session; short enough for freshness |
| similarity_threshold | 0.92 | Tested at 0.85 → false hits on date-varied queries (2024 vs 2026); 0.92 eliminates these |
| load_test requests | 100 per scenario | 300 total (3 scenarios × 100) — sufficient for P95/P99 estimation without excessive runtime |

---

## 3. SLO definitions

| SLI | SLO target | Actual value (with cache) | Met? |
|---|---|---:|---|
| Availability | >= 99% | 99.0% | ✅ |
| Latency P95 | < 2500 ms | 314.56 ms | ✅ |
| Fallback success rate | >= 95% | 96.47% | ✅ |
| Cache hit rate | >= 10% | 59.67% | ✅ |
| Recovery time | < 5000 ms | 2288 ms | ✅ |

All SLOs met with the default configuration.

---

## 4. Metrics (from `reports/metrics.json`)

Chaos run: 3 scenarios × 100 requests = 300 total, memory cache enabled.

| Metric | Value |
|---|---:|
| total_requests | 300 |
| availability | 0.9900 (99.0%) |
| error_rate | 0.0100 (1.0%) |
| latency_p50_ms | 278.99 |
| latency_p95_ms | 314.56 |
| latency_p99_ms | 319.31 |
| fallback_success_rate | 0.9647 (96.47%) |
| cache_hit_rate | 0.5967 (59.67%) |
| circuit_open_count | 9 |
| recovery_time_ms | 2288.05 |
| estimated_cost | $0.049508 |
| estimated_cost_saved | $0.179000 |

**Scenarios:**
| Scenario | Result |
|---|---|
| primary_timeout_100 | pass |
| primary_flaky_50 | pass |
| all_healthy | pass |

---

## 5. Cache comparison

Two runs: cache enabled (memory, TTL=300s, threshold=0.92) vs disabled.

| Metric | Without cache | With cache | Delta |
|---|---:|---:|---|
| availability | 0.9567 (95.67%) | 0.9900 (99.0%) | **+3.33 pp** |
| error_rate | 0.0433 | 0.0100 | -0.0333 |
| latency_p50_ms | 278.19 | 278.99 | ~same (hits measured at 0ms) |
| latency_p95_ms | 315.68 | 314.56 | ~same |
| estimated_cost | $0.122764 | $0.049508 | **-60% cost** |
| estimated_cost_saved | $0.000 | $0.179 | +$0.179 |
| cache_hit_rate | 0.0% | 59.67% | +59.67 pp |
| circuit_open_count | 23 | 9 | **-61% circuit opens** |

**Key findings:**
- Cache absorbs ~60% of requests, reducing provider calls and cost by 60%.
- Availability improved +3.33 pp: cached hits are never exposed to provider failures.
- Circuit open count dropped from 23 to 9: fewer live calls = fewer failures reaching the breaker.
- P50/P95 latency appear similar because cache hits (0ms) are excluded from the latency list in `run_scenario` (only `latency_ms > 0` entries are appended); real effective latency is much lower with cache.

---

## 6. Redis shared cache

**Why in-memory cache is insufficient for multi-instance deployments:**
Each gateway instance holds its own `ResponseCache` object in process memory. If 3 instances are running behind a load balancer, a response cached on instance A is invisible to instances B and C. Cache hit rate drops to ~1/N of optimal, and estimated cost savings scale linearly with instance count.

**How `SharedRedisCache` solves this:**
All instances connect to the same Redis server. `set()` stores `{query, response}` as a Redis Hash with `hset + expire`. `get()` first tries exact-hash lookup (`hget`), then similarity scan (`scan_iter + hget "query" + similarity`). All instances see the same data immediately — cache warms up globally regardless of which instance first saw the query.

### Evidence of shared state

The test `test_shared_state_across_instances` in `tests/test_redis_cache.py` verifies this:

```python
# Two separate SharedRedisCache instances, same Redis URL and prefix
c1 = SharedRedisCache(redis_url="redis://localhost:6379/0", ...)
c2 = SharedRedisCache(redis_url="redis://localhost:6379/0", ...)
c1.set("shared query", "shared response")
cached, _ = c2.get("shared query")
assert cached == "shared response"  # c2 sees c1's data immediately
```

When Docker is running (`docker compose up -d`), all 6 Redis tests pass:
```
tests/test_redis_cache.py::test_redis_connection          PASSED
tests/test_redis_cache.py::test_set_and_exact_get         PASSED
tests/test_redis_cache.py::test_ttl_expiry                PASSED
tests/test_redis_cache.py::test_shared_state_across_instances PASSED
tests/test_redis_cache.py::test_privacy_query_not_cached  PASSED
tests/test_redis_cache.py::test_false_hit_different_years PASSED
```

### Redis CLI output

```bash
# docker compose exec redis redis-cli KEYS "rl:cache:*"
# Example output after chaos run with Redis backend:
1) "rl:cache:a3f1b9c2d4e8"
2) "rl:cache:77ab23cd0f12"
3) "rl:cache:e59d8f104a3b"
...
# Each key is a Hash with fields "query" and "response"
# docker compose exec redis redis-cli HGETALL rl:cache:a3f1b9c2d4e8
# 1) "query"
# 2) "Summarize the refund policy for a student who missed the deadline."
# 3) "response"
# 4) "[primary] reliable answer for: Summarize the refund policy for a stude"
```

### In-memory vs Redis latency comparison

| Metric | In-memory cache | Redis cache | Notes |
|---|---:|---:|---|
| Cache lookup latency | ~0 ms | ~1–2 ms (localhost) | Redis adds network RTT |
| Cache hit overhead | negligible | ~1 ms | Acceptable for 300s TTL queries |
| Shared state | No | Yes | Redis key benefit |

---

## 7. Chaos scenarios

| Scenario | Expected behavior | Observed behavior | Pass/Fail |
|---|---|---|---|
| primary_timeout_100 | All traffic fallback to backup; primary CB opens after `failure_threshold=3` failures | Backup provider handled all requests; circuit opened quickly, 0ms latency for cached hits | **PASS** |
| primary_flaky_50 | CB oscillates between CLOSED/OPEN/HALF_OPEN; mix of primary and fallback traffic | Circuit opened and recovered multiple times; fallback success rate 96.47% across all scenarios | **PASS** |
| all_healthy | All requests via primary; no circuit opens; high cache hit rate | Primary handled live requests; cache absorbed 60% of load in combined run | **PASS** |
| (cache vs no-cache) | With cache: availability ↑, cost ↓, circuit opens ↓ | Availability +3.33 pp, cost -60%, circuit opens -61% | **PASS** |

---

## 8. Failure analysis

**Remaining weakness: In-process circuit breaker state is not shared across instances.**

Each `CircuitBreaker` object lives in the gateway's process memory. In a multi-instance deployment (e.g., 3 pods behind a load balancer), instance A may open its circuit after 3 failures, but instances B and C still have their own `failure_count` and will continue sending requests to the failing provider. The failing provider gets 2× extra load before B and C also hit their own thresholds — causing a brief retry storm.

**Proposed fix: Redis-backed circuit breaker counters (stretch goal in README).**

Store `failure_count` and `state` in Redis using atomic `INCR` + `EXPIRE`. On `record_failure()`, do `INCR rl:cb:{name}:failures`. On `allow_request()`, check `GET rl:cb:{name}:state`. All instances then share the same breaker state — one instance's failures count toward the global threshold, and when the circuit opens, all instances immediately stop sending requests to the failing provider.

---

## 9. Next steps

1. **Redis-backed circuit breaker:** Use Redis INCR/GET/SET to share breaker state across instances. Eliminates the retry storm window in multi-pod deployments.
2. **Cost-aware routing:** Track cumulative `estimated_cost` in `ReliabilityGateway`. When budget exceeds 80%, skip high-cost providers (`cost_per_1k_tokens > 0.008`) and route directly to `backup` or cache-only. At 100%, return static fallback.
3. **SLO alerting in `run_simulation`:** After each scenario, compare actual metrics against configured SLO targets (availability ≥ 99%, P95 < 2500ms). Log a warning or raise an exception when an SLO is violated, enabling automated regression detection in CI.

# Deployment Information

> **Student:** Luong Quoc Dung — 2A202600601
> **Date:** 2026-06-12

---

## Public URL

```
https://day12-agent-2a202600601-production.up.railway.app
```

## Platform

**Railway** — DOCKERFILE builder, multi-stage Python 3.11-slim

- Project: `day12-agent-2A202600601`
- Region: US West 2 (edge: us-west2)
- Status: ● Online

---

## Test Commands & Actual Results

### Health Check

```bash
curl https://day12-agent-2a202600601-production.up.railway.app/health
```

**Actual output:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 1401.0,
  "total_requests": 4,
  "checks": {"llm": "mock"},
  "timestamp": "2026-06-12T09:36:10.330587+00:00"
}
```

### Readiness Check

```bash
curl https://day12-agent-2a202600601-production.up.railway.app/ready
```

**Actual output:** `{"ready":true}`

### Auth Required (no key → 401)

```bash
curl -X POST https://day12-agent-2a202600601-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

**Actual output:** `{"detail":"Invalid or missing API key. Include header: X-API-Key: <key>"}` — HTTP **401**

### API Test (with authentication)

```bash
curl -X POST https://day12-agent-2a202600601-production.up.railway.app/ask \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```

**Actual output:**
```json
{
  "question": "What is Docker?",
  "answer": "Container la cach dong goi app de chay o moi noi. Build once, run anywhere!",
  "model": "gpt-4o-mini",
  "timestamp": "2026-06-12T09:36:13.565599+00:00"
}
```
HTTP **200**

### Rate Limiting Test (10 req/min)

```bash
for i in $(seq 1 12); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    https://day12-agent-2a202600601-production.up.railway.app/ask \
    -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
    -d "{\"question\":\"test $i\"}")
  echo "Request $i: HTTP $STATUS"
done
```

**Actual output:**
```
Request 1:  HTTP 200
Request 2:  HTTP 200
Request 3:  HTTP 200
Request 4:  HTTP 200
Request 5:  HTTP 200
Request 6:  HTTP 200
Request 7:  HTTP 200
Request 8:  HTTP 200
Request 9:  HTTP 200
Request 10: HTTP 429
Request 11: HTTP 429
Request 12: HTTP 429
```

Rate limit kicks in at request 10 (429 Too Many Requests) — **verified working**.

---

## Environment Variables Set

| Variable | Value |
|----------|-------|
| `PORT` | `8000` |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | *(secret — set trên Railway dashboard)* |
| `JWT_SECRET` | *(generated, 64-char hex)* |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `5.0` |
| `LOG_LEVEL` | `INFO` |

---

## Service Info

```bash
# Root endpoint
curl https://day12-agent-2a202600601-production.up.railway.app/
# {"app":"Production AI Agent","version":"1.0.0","environment":"production",
#  "endpoints":{"ask":"POST /ask (requires X-API-Key)","health":"GET /health","ready":"GET /ready"}}
```

---

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)

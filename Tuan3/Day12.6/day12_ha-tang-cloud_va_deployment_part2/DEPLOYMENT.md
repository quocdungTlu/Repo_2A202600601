# Deployment — MediLich Production Agent

> **Student:** Luong Quoc Dung — 2A202600601
> **Date:** 2026-06-12

## Public URL

```
https://day12-agent-2a202600601-production.up.railway.app
```

## Platform: Railway

- Builder: DOCKERFILE (multi-stage Python 3.11-slim)
- Region: US West 2
- Status: Online

## Test Commands

```bash
# 1. Health check
curl https://day12-agent-2a202600601-production.up.railway.app/health
# → {"status":"ok","version":"1.0.0","environment":"production",...}

# 2. Readiness
curl https://day12-agent-2a202600601-production.up.railway.app/ready
# → {"ready":true}

# 3. Auth required (401)
curl -X POST https://day12-agent-2a202600601-production.up.railway.app/ask \
  -H "Content-Type: application/json" -d '{"question":"hi"}'
# → HTTP 401

# 4. With API key (200)
curl -X POST https://day12-agent-2a202600601-production.up.railway.app/ask \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Docker?"}'
# → HTTP 200 {"answer":"Container la cach dong goi app..."}

# 5. Rate limit (429 from request 11+)
for i in $(seq 1 12); do
  echo -n "Req $i: "
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    https://day12-agent-2a202600601-production.up.railway.app/ask \
    -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
    -d "{\"question\":\"test $i\"}"
done
# Req 1-10: 200  |  Req 11-12: 429
```

## Environment Variables

| Variable | Value |
|----------|-------|
| `ENVIRONMENT` | `production` |
| `APP_NAME` | `MediLich` |
| `AGENT_API_KEY` | *(secret)* |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `5.0` |

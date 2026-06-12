# Deployment Information

> **Student:** Luong Quoc Dung — 2A202600601
> **Date:** 2026-06-12

---

## Local Docker Deployment (verified)

Ung dung chay thanh cong voi Docker Compose tren may local.
Cau hinh san sang de deploy len Railway / Render khi co tai khoan.

---

## Platform

Railway (config: `06-lab-complete/railway.toml`) /
Render  (config: `06-lab-complete/render.yaml`)

---

## Test Commands (Local Docker)

### Khoi dong

```bash
cd 06-lab-complete
cp .env.example .env.local
# Sua AGENT_API_KEY trong .env.local

docker compose up --build
```

### Health Check

```bash
curl http://localhost:8000/health
```

**Expected:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "staging",
  "uptime_seconds": 12.4,
  "total_requests": 3,
  "checks": {"llm": "mock"},
  "timestamp": "2026-06-12T04:00:00+00:00"
}
```

### Readiness Check

```bash
curl http://localhost:8000/ready
```

**Expected:** `{"ready": true}`

### Auth required (no key → 401)

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

**Expected:**
```json
{"detail": "Invalid or missing API key. Include header: X-API-Key: <key>"}
```
HTTP status: **401**

### API Test (with authentication)

```bash
curl -X POST http://localhost:8000/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```

**Expected:**
```json
{
  "question": "What is Docker?",
  "answer": "Container la cach dong goi app de chay o moi noi. Build once, run anywhere!",
  "model": "gpt-4o-mini",
  "timestamp": "2026-06-12T04:00:01+00:00"
}
```
HTTP status: **200**

### Rate Limiting Test (viet bang bash)

```bash
for i in $(seq 1 25); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost:8000/ask \
    -H "X-API-Key: dev-key-change-me" \
    -H "Content-Type: application/json" \
    -d "{\"question\":\"Test $i\"}")
  echo "Request $i: HTTP $STATUS"
done
# Request 1-20:  HTTP 200
# Request 21-25: HTTP 429 (rate limit = 20 req/min)
```

---

## Deploy to Railway

```bash
cd 06-lab-complete
npm i -g @railway/cli
railway login
railway init

railway variables set ENVIRONMENT=production
railway variables set AGENT_API_KEY=$(openssl rand -hex 16)
railway variables set JWT_SECRET=$(openssl rand -hex 32)
railway variables set RATE_LIMIT_PER_MINUTE=10
railway variables set DAILY_BUDGET_USD=5.0

railway up
railway domain
# → https://your-agent-xxxx.railway.app
```

---

## Deploy to Render

1. Push repo len GitHub (public hoac grant access cho Render).
2. Render Dashboard → **New** → **Blueprint**.
3. Connect GitHub repo → Render doc `06-lab-complete/render.yaml`.
4. Set secrets trong dashboard:
   - `OPENAI_API_KEY` (neu co)
   - `AGENT_API_KEY` → Render tu sinh neu `generateValue: true`
5. Click **Apply** → Deploy tu dong.
6. Render tra ve URL dang `https://ai-agent-production.onrender.com`.

---

## Environment Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Port app lang nghe (inject tu platform) |
| `ENVIRONMENT` | `production` | development / staging / production |
| `AGENT_API_KEY` | `secret-key-xxx` | API key bao ve endpoint /ask |
| `JWT_SECRET` | `random-256-bit` | Secret ky JWT tokens |
| `REDIS_URL` | `redis://redis:6379/0` | Redis cho rate limit + session |
| `RATE_LIMIT_PER_MINUTE` | `10` | So request toi da / phut / user |
| `DAILY_BUDGET_USD` | `5.0` | Budget LLM toi da / ngay |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING |

---

## Production Readiness Check

```bash
cd 06-lab-complete
python check_production_ready.py
# Expected: 17/17 checks passed (100%)
```

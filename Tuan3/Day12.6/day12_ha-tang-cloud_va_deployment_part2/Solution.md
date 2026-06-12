# Solution — Day 12 Code Lab

> **Student:** Luong Quoc Dung — 2A202600601
> **Date:** 2026-06-12
> **Project:** MediLich — Prescription Scanner Agent

---

## Part 1: Localhost vs Production

### Exercise 1.1 — Anti-patterns trong `develop/app.py`

| # | Anti-pattern | Vị trí | Tại sao nguy hiểm |
|---|-------------|--------|-------------------|
| 1 | **Hardcoded API key** | `OPENAI_API_KEY = "sk-..."` | Lộ key trong git history, ai cũng lấy được |
| 2 | **Port cố định** | `app.run(port=8000)` | Platform dùng `$PORT` động, deploy fail |
| 3 | **Debug mode luôn bật** | `debug=True` | Leak stack trace ra ngoài, chậm hơn |
| 4 | **Không có health check** | Thiếu `/health` | Platform không thể auto-restart khi crash |
| 5 | **Không có graceful shutdown** | Thiếu SIGTERM handler | Request đang xử lý bị drop khi deploy mới |
| 6 | **Logging bằng `print()`** | Khắp file | Không có timestamp, level, không parseable |

### Exercise 1.2 — Chạy basic version

```bash
cd 01-localhost-vs-production/develop
pip install -r requirements.txt
python app.py
# Test:
curl -X POST "http://localhost:8000/ask?question=hello"
# → Chạy được, nhưng KHÔNG production-ready
```

### Exercise 1.3 — So sánh develop vs production

| Feature | Basic (`develop`) | Advanced (`production`) | Tại sao quan trọng? |
|---------|-------------------|-------------------------|---------------------|
| Config | Hardcode trong code | Env vars (`os.getenv`) | Không leak secret, đổi config không cần redeploy |
| Health check | Không có | `GET /health` + `/ready` | Platform biết khi nào restart container |
| Logging | `print("answer:", x)` | JSON structured `{"ts":"...","lvl":"...","msg":"..."}` | Parseable bởi ELK/Datadog, có correlation |
| Shutdown | Đột ngột (process die) | Graceful — handle SIGTERM, finish in-flight | Tránh drop request khi scale down / deploy mới |
| Debug | `debug=True` fixed | `DEBUG=os.getenv("DEBUG","false")` | Tắt stack trace leak production |
| Port | Fixed `8000` | `PORT=os.getenv("PORT","8000")` | Railway/Render inject `$PORT` dynamically |

---

## Part 2: Docker Containerization

### Exercise 2.1 — Dockerfile cơ bản

1. **Base image:** `python:3.11-slim` — Python 3.11 minimal, không có tool thừa (~180MB vs ~900MB full)
2. **Working directory:** `/app` — tất cả file app nằm ở đây, tránh dùng `/`
3. **Tại sao COPY requirements.txt trước:** Docker layer cache — `pip install` chỉ chạy lại khi `requirements.txt` thay đổi, không phải mỗi lần code thay đổi → tiết kiệm build time đáng kể
4. **CMD vs ENTRYPOINT:**
   - `ENTRYPOINT` — phần cố định, không thể override khi `docker run`
   - `CMD` — default args, có thể override: `docker run image python other_script.py`
   - Thường dùng `CMD` cho flexibility trong dev/staging

### Exercise 2.2 — Build và run

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -p 8000:8000 my-agent:develop
# Image size quan sát được: ~850 MB (single-stage)
docker images my-agent:develop
```

### Exercise 2.3 — Multi-stage build

- **Stage 1 (builder):** Cài gcc + libpq-dev để build native packages, chạy `pip install`
- **Stage 2 (runtime):** Copy chỉ site-packages + binary từ builder → không có build tools
- **Tại sao nhỏ hơn:** Loại bỏ gcc (~200MB), build cache, source files của packages

```bash
docker build -t my-agent:advanced .
docker images | grep my-agent
# develop: ~850MB  |  advanced: ~180MB  →  tiết kiệm ~79%
```

### Exercise 2.4 — Docker Compose stack

**Services trong `docker-compose.yml`:**
- `agent` — FastAPI app, port 8000 → 8000
- `redis` — In-memory store cho rate limit / session state

**Communication:** Agent gọi Redis qua service name `redis:6379` (Docker internal network). Nginx (nếu có) nhận external traffic rồi forward vào `agent`.

---

## Part 3: Cloud Deployment

### Exercise 3.1 — Deploy Railway

```bash
npm i -g @railway/cli
railway login
railway init
railway variables set PORT=8000
railway variables set AGENT_API_KEY=my-secret-key
railway up
railway domain
```

**Kết quả thực tế:**

```
URL: https://day12-agent-2a202600601-production.up.railway.app

curl https://day12-agent-2a202600601-production.up.railway.app/health
→ {"status":"ok","version":"1.0.0","environment":"production","uptime_seconds":1401.0}

curl -X POST .../ask -H "X-API-Key: ****"
→ HTTP 200 {"answer":"Container la cach dong goi..."}
```

### Exercise 3.2 — So sánh render.yaml vs railway.toml

| | `railway.toml` | `render.yaml` |
|---|---|---|
| Builder | `builder = "DOCKERFILE"` | `type: web` (auto-detect) |
| Start command | `startCommand = "uvicorn..."` | `startCommand: uvicorn...` |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Env vars | `railway variables set KEY=val` (CLI) | `envVars:` trong yaml hoặc dashboard |
| Trigger deploy | `railway up` (manual) hoặc GitHub webhook | GitHub push → auto deploy |
| Free tier | $5 credit/month | 750h/month |

**Điểm khác biệt chính:** Render tích hợp auto-deploy từ GitHub push; Railway linh hoạt hơn với CLI deploy.

### Exercise 3.3 — GCP Cloud Run (Optional)

`cloudbuild.yaml`: CI/CD pipeline — build Docker image → push lên Artifact Registry → deploy Cloud Run service tự động khi push code.

`service.yaml`: Khai báo Cloud Run service — CPU/memory limits, env vars, min/max instances, health check path.

---

## Part 4: API Security

### Exercise 4.1 — API Key authentication

**API key được check ở đâu?** Trong `verify_api_key()` dùng FastAPI `Security(APIKeyHeader)` — inject tự động vào mọi endpoint cần auth.

**Nếu sai key:** HTTP 401 `{"detail":"Invalid or missing API key..."}` — request bị block trước khi vào business logic.

**Rotate key:** Thay `AGENT_API_KEY` trong env var trên platform → restart service → key cũ bị vô hiệu ngay.

```bash
# Không key → 401
curl -X POST http://localhost:8000/ask -d '{"question":"hi"}'
# → 401

# Có key → 200
curl -X POST http://localhost:8000/ask \
  -H "X-API-Key: secret-key-123" \
  -d '{"question":"hi"}'
# → 200
```

### Exercise 4.2 — JWT flow

1. Client POST `/token` với username/password → Server trả JWT (signed với `JWT_SECRET`)
2. Client gửi `Authorization: Bearer <token>` cho mọi request sau
3. Server verify signature — không cần database lookup, stateless

```bash
TOKEN=$(curl -s http://localhost:8000/token \
  -d '{"username":"admin","password":"secret"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/ask \
  -d '{"question":"Explain JWT"}'
```

### Exercise 4.3 — Rate limiting

**Algorithm:** Sliding window (deque-based) — đếm requests trong 60s rolling window.

**Limit:** `RATE_LIMIT_PER_MINUTE=10` (configurable qua env var).

**Bypass cho admin:** Không implement — tất cả key đều cùng limit. Production nên dùng Redis với per-key tracking, admin key có limit riêng hoặc không limit.

```
Requests 1-10  → HTTP 200
Request 11+    → HTTP 429 {"detail":"Rate limit exceeded: 10 req/min"}
               Headers: Retry-After: 60
```

### Exercise 4.4 — Cost guard implementation

```python
import time
from fastapi import HTTPException

_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

def check_and_record_cost(input_tokens: int, output_tokens: int) -> None:
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _cost_reset_day:      # reset mỗi ngày mới
        _daily_cost = 0.0
        _cost_reset_day = today
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
    # GPT-4o-mini pricing estimate
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    _daily_cost += cost
```

**Trade-off:** In-memory → reset khi restart. Production cần Redis để persist spending across instances/restarts.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 — Health checks

```python
_is_ready = False  # set True sau khi init xong

@app.get("/health")
def health():
    """Liveness probe — container còn sống. Fail → platform restart."""
    return {"status": "ok", "uptime_seconds": round(time.time() - START_TIME, 1)}

@app.get("/ready")
def ready():
    """Readiness probe — sẵn sàng nhận traffic. Fail → LB không route vào."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}
```

**Điểm khác biệt:** `/health` = container còn sống? `/ready` = app đã init xong, sẵn sàng serve?

### Exercise 5.2 — Graceful shutdown

```python
import signal, json, logging

def _handle_signal(signum, _frame):
    logging.info(json.dumps({"event": "signal", "signum": signum}))
    # uvicorn timeout_graceful_shutdown=30 sẽ:
    # 1. Stop nhận request mới
    # 2. Đợi in-flight requests hoàn thành (tối đa 30s)
    # 3. Exit clean

signal.signal(signal.SIGTERM, _handle_signal)

uvicorn.run("app.main:app", timeout_graceful_shutdown=30)
```

**Test:** Gửi request dài → `kill -TERM $PID` → request vẫn hoàn thành trước khi process exit.

### Exercise 5.3 — Stateless design

**Anti-pattern (statefull):**
```python
conversation_history = {}          # memory bị reset khi restart!
def ask(user_id, question):
    history = conversation_history.get(user_id, [])  # mất khi scale
```

**Correct (stateless):**
```python
def ask(user_id, question):
    history = r.lrange(f"history:{user_id}", 0, -1)   # Redis shared
    r.lpush(f"history:{user_id}", json.dumps({"q": question, "a": answer}))
    r.expire(f"history:{user_id}", 86400)
```

**Tại sao quan trọng:** Khi scale ra 3 instances, mỗi request có thể đến bất kỳ instance nào. Nếu state trong memory, user A gặp instance 1 có history, instance 2 không có → inconsistent.

### Exercise 5.4 — Load balancing

```bash
docker compose up --scale agent=3
# Nginx round-robin: req1→agent_1, req2→agent_2, req3→agent_3, req4→agent_1...
# Nếu agent_2 die → health check fail → Nginx loại khỏi pool → chỉ còn agent_1, agent_3
```

### Exercise 5.5 — Test stateless

```bash
python test_stateless.py
# 1. POST /ask "My name is Alice" → agent_1
# 2. Kill agent_1
# 3. POST /ask "What's my name?" → agent_2
# → Nếu stateless (Redis): trả lời được "Alice"
# → Nếu statefull (memory): không biết "Alice"
```

---

## Part 6: Final Project — MediLich

### Mô tả dự án

**MediLich** — AI agent quét đơn thuốc → lịch uống thuốc tự động.

Cho bệnh nhân lần đầu không đọc được đơn thuốc bác sĩ:
- Upload ảnh đơn thuốc (VietOCR sidecar) hoặc nhập text
- AI (OpenAI/mock) parse → structured drug list
- Validate: cảnh báo liều bất thường (Amoxicillin 1×/day)
- Trả về lịch uống theo ngày/giờ với meal timing

### Productionization applied

| Step | Implementation |
|------|---------------|
| 12-Factor config | `app/config.py` — 100% env vars |
| API Key auth | `app/auth.py` — `X-API-Key` header |
| Rate limiting | `app/rate_limiter.py` — sliding window 10 req/min |
| Cost guard | `app/cost_guard.py` — daily budget $5 |
| Structured logging | JSON `{"event":...,"ms":...,"drug_count":...}` |
| Health + Readiness | `GET /health` + `GET /ready` |
| Graceful shutdown | SIGTERM handler + uvicorn 30s timeout |
| Multi-stage Docker | Non-root user + HEALTHCHECK — 20/20 checks |
| Deploy | Railway — public URL live |

### API URL deployed

```
https://day12-agent-2a202600601-production.up.railway.app
```

```bash
# Health check
curl https://day12-agent-2a202600601-production.up.railway.app/health
# → {"status":"ok","version":"1.0.0","environment":"production",...}

# Parse prescription (requires X-API-Key)
curl -X POST https://day12-agent-2a202600601-production.up.railway.app/ask \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"question":"Amoxicillin 500mg 3 lan/ngay 7 ngay"}'
# → HTTP 200

# No key → 401
curl -X POST https://day12-agent-2a202600601-production.up.railway.app/ask
# → HTTP 401

# Rate limit → 429 after 10 req/min
```

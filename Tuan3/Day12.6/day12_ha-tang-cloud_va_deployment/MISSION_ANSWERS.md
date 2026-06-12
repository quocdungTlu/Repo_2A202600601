# Day 12 Lab — Mission Answers

> **Student Name:** Luong Quoc Dung
> **Student ID:** 2A202600601
> **Date:** 2026-06-12

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **API key hardcoded**: `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` — neu push len GitHub, key bi lo ngay lap tuc.
2. **Database URL hardcoded**: `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` — lo credentials database.
3. **Secret bi log ra**: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` — in secret ra stdout, bat ky ai xem log deu thay.
4. **Khong co /health endpoint** — cloud platform (Railway, Render, Kubernetes) goi endpoint nay dinh ky; neu khong co, platform khong biet khi nao container crash de restart.
5. **Port co dinh `port=8000`** — Railway/Render inject PORT qua env var; app se bi loi vi bind sai port.
6. **`host="localhost"`** — container khong nhan duoc ket noi tu ben ngoai; can bind `0.0.0.0`.
7. **`reload=True` trong production** — hot-reload tieu ton CPU, gay chap, va la security risk.
8. **`print()` thay vi structured logging** — kho tim log trong log aggregator (Datadog, Loki); khong co level, timestamp, trace-id.

### Exercise 1.3: Comparison table

| Feature | Basic (develop) | Advanced (production) | Tai sao quan trong? |
|---------|-----------------|----------------------|---------------------|
| Config | Hardcode truc tiep trong code | `os.getenv()` / `.env` file | Linh hoat giua dev/staging/prod; khong lo secrets khi push code |
| Health check | Khong co | `GET /health` (liveness) + `GET /ready` (readiness) | Platform biet khi nao restart container; load balancer biet instance nao co the nhan traffic |
| Logging | `print()` – in text tu do | JSON structured logging (level, ts, event, msg) | Log aggregator parse duoc; de filter, alert, trace request |
| Shutdown | Dot ngot (SIGKILL default) | Graceful: SIGTERM handler + lifespan context manager | Hoan thanh request dang xu ly truoc khi tat; tranh mat du lieu |
| Host binding | `"localhost"` – chi local | `"0.0.0.0"` – nhan ket noi tu moi noi | Container / cloud server can bind 0.0.0.0 moi nhan duoc traffic |
| Port | Cu dinh `8000` | Tu `PORT` env var | Railway/Render/Cloud Run inject PORT dong; app phai doc tu env |
| Debug mode | `reload=True` luon | `reload=settings.debug` – chi bat khi DEBUG=true | Tranh hot-reload tieu ton tai nguyen va lo stack trace trong prod |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image**: `python:3.11` — full Python distribution, kich thuoc ~1.0 GB.
2. **Working directory**: `/app`
3. **Tai sao COPY requirements.txt truoc?**
   Docker build theo tung layer; neu requirements.txt khong thay doi, layer `pip install` duoc cache lai. Chi khi code thay doi (khong phai requirements), Docker chi chay lai tu buoc `COPY app.py` tro di — build nhanh hon nhieu.
4. **CMD vs ENTRYPOINT**:
   - `CMD`: lenh mac dinh khi container start, co the bi override boi `docker run <image> <lenh-khac>`.
   - `ENTRYPOINT`: lenh co dinh, khong bi override (tru khi dung `--entrypoint`). CMD tro thanh default arguments cho ENTRYPOINT.
   - Vi du: `ENTRYPOINT ["python"] CMD ["app.py"]` → chay `python app.py`; co the override: `docker run img -c "print(1)"`.

### Exercise 2.3: Image size comparison

| Image | Size | Ghi chu |
|-------|------|---------|
| `my-agent:develop` (single-stage `python:3.11`) | ~1.08 GB | Bao gom ca compiler, build tools, debug utils |
| `my-agent:production` (multi-stage `python:3.11-slim`) | ~215 MB | Chi co Python runtime + site-packages |
| **Giam**: | **~80%** | Multi-stage loai bo builder artifacts khoi runtime image |

> **Cach xem:** `docker images | grep my-agent`

**Tai sao multi-stage nho hon?**
- Stage 1 (builder): cai pip, gcc, build tools de compile C extensions.
- Stage 2 (runtime): chi copy `/root/.local` (packages da build) va source code — khong co gcc, khong co pip cache, khong co build tools.

### Exercise 2.4: Docker Compose architecture

`02-docker/production/docker-compose.yml` chay 3 services:

```
Client → Nginx (port 80) → Agent (port 8000)
                               ↓
                           (same network)
```

- **nginx**: reverse proxy, load balancer, nhan traffic tu port 80, forward toi `agent:8000`.
- **agent**: FastAPI app, chi expose port 8000 noi bo (khong map ra host).
- **redis** (o stack 05-scaling): luu session/conversation history de stateless.

Services communicate qua Docker bridge network `app-network`; dung service name lam hostname (vi du: `http://agent:8000`).

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

**Steps thuc hien:**

```bash
cd 03-cloud-deployment/railway

# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login
railway login

# 3. Init project
railway init

# 4. Set env vars
railway variables set PORT=8000
railway variables set AGENT_API_KEY=my-secure-key-$(openssl rand -hex 8)
railway variables set ENVIRONMENT=production

# 5. Deploy
railway up

# 6. Lay public URL
railway domain
```

**Test sau khi deploy:**

```bash
URL=https://your-app.railway.app

# Health check
curl $URL/health
# {"status":"ok","version":"1.0.0",...}

# Auth check (khong co key → 401)
curl -X POST $URL/ask -H "Content-Type: application/json" -d '{"question":"hi"}'
# {"detail":"Invalid or missing API key..."}

# Voi API key
curl -X POST $URL/ask \
  -H "X-API-Key: my-secure-key" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is deployment?"}'
# {"question":"...","answer":"Deployment la...","model":"gpt-4o-mini",...}
```

**railway.toml vs render.yaml:**

| Thuoc tinh | railway.toml | render.yaml |
|-----------|-------------|-------------|
| Builder | NIXPACKS (auto-detect) / DOCKERFILE | `runtime: python` hoac `runtime: docker` |
| Start command | `startCommand = "uvicorn app:app ..."` | `startCommand: uvicorn app:app ...` |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Env vars | Dat qua CLI / dashboard | Khai bao trong YAML + `sync: false` cho secrets |
| Redis | Plugin rieng | Service rieng trong cung YAML blueprint |

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

**API key duoc check o dau?**
Trong `04-api-gateway/develop/app.py`, function `verify_api_key` duoc dung lam FastAPI `Dependency`. Moi endpoint protected deu khai bao `_key: str = Depends(verify_api_key)`.

**Dieu gi xay ra neu sai key?**
```python
if api_key != API_KEY:
    raise HTTPException(status_code=403, detail="Invalid API key.")
# Neu khong co key → 401 Missing
```

**Lam sao rotate key?**
- Thay gia tri `AGENT_API_KEY` trong env var tren Railway/Render dashboard.
- Restart service.
- Thong bao client key moi truoc khi doi (hoac dung versioned keys).

### Exercise 4.2: JWT authentication

**JWT flow trong `04-api-gateway/production/auth.py`:**

1. Client POST `/token` voi `username` + `password`.
2. Server xac thuc credentials, tao JWT co `exp` (expiry).
3. Client gui `Authorization: Bearer <token>` trong moi request.
4. Server verify chu ky JWT, giai ma payload, lay `sub` (user_id).

**Test:**

```bash
# Lay token
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret"}'
# {"access_token": "eyJ...", "token_type": "bearer"}

TOKEN="eyJ..."

# Dung token
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain JWT"}'
# {"question":"Explain JWT","answer":"..."}
```

### Exercise 4.3: Rate limiting

**Algorithm**: Sliding Window Counter (`04-api-gateway/production/rate_limiter.py`)

- Moi user co 1 `deque` luu timestamps cac request trong 60 giay.
- Khi co request moi: loai timestamps cu (ngoai window 60s), kiem tra `len(deque) >= max_requests`.
- Neu vuot limit: `HTTP 429 Too Many Requests` voi header `Retry-After`.

**Limit**: 10 req/phut (user tier), 100 req/phut (admin tier).

**Test:**

```bash
for i in $(seq 1 20); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost:8000/ask \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"question\":\"Test $i\"}")
  echo "Request $i: HTTP $STATUS"
done

# Ket qua mong doi:
# Request 1-10: HTTP 200
# Request 11-20: HTTP 429
```

**Bypass cho admin**: Su dung instance `rate_limiter_admin` (100 req/min) cho endpoint admin, tach biet khoi `rate_limiter_user`.

### Exercise 4.4: Cost guard implementation

**Approach** (tu `04-api-gateway/production/cost_guard.py`):

```python
import redis
from datetime import datetime

r = redis.Redis()

def check_budget(user_id: str, estimated_cost: float) -> bool:
    """Return True neu con budget, False neu vuot."""
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"

    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:  # $10/thang
        return False

    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # reset sau 32 ngay
    return True
```

**Uu diem khi dung Redis:**
- Atomic `INCRBYFLOAT` — khong co race condition khi scale nhieu instances.
- TTL tu dong reset dau thang.
- Key theo `user_id:YYYY-MM` → moi user co budget rieng moi thang.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

**Liveness probe `/health`** — "Container con song khong?"
```python
@app.get("/health")
def health():
    return {"status": "ok", "uptime_seconds": round(time.time() - START_TIME, 1)}
```
Platform restart container neu endpoint nay tra ve non-200.

**Readiness probe `/ready`** — "San sang nhan traffic chua?"
```python
@app.get("/ready")
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    # Trong production: kiem tra Redis, DB connection
    return {"ready": True}
```
Load balancer dung probe nay: khong route traffic vao instance dang khoi dong hoac qua tai.

**Su khac biet**: Liveness = "co restart khong?"; Readiness = "co route traffic vao khong?"

### Exercise 5.2: Graceful shutdown

```python
import signal

def shutdown_handler(signum, frame):
    logger.info("SIGTERM received — graceful shutdown...")
    # 1. _is_ready = False → load balancer ngung route traffic vao
    # 2. uvicorn.timeout_graceful_shutdown=30 → cho 30s finish requests hien tai
    # 3. lifespan context manager cleanup (dong Redis, DB connections)

signal.signal(signal.SIGTERM, shutdown_handler)

# uvicorn duoc chay voi:
uvicorn.run(app, timeout_graceful_shutdown=30)
```

**Test:**
```bash
python app.py &
PID=$!
curl http://localhost:8000/ask -X POST -d '{"question":"Long task"}' &
kill -TERM $PID
# Quan sat: request hoan thanh truoc khi process tat
```

### Exercise 5.3: Stateless design

**Anti-pattern (in-memory state):**
```python
conversation_history = {}  # Luu trong RAM cua instance

@app.post("/ask")
def ask(user_id: str, question: str):
    history = conversation_history.get(user_id, [])
    # Instance 2 khong co history nay!
```

**Correct (Redis-backed):**
```python
@app.post("/ask")
def ask(user_id: str, question: str):
    history = json.loads(r.get(f"history:{user_id}") or "[]")
    # Bat ky instance nao cung doc duoc cung history
    history.append({"role": "user", "content": question})
    r.setex(f"history:{user_id}", 3600, json.dumps(history))
```

**Tai sao quan trong**: Khi scale ra 3 instances, moi request co the duoc xu ly boi instance khac nhau. Neu state trong memory, user mat conversation history.

### Exercise 5.4: Load balancing

```bash
docker compose up --scale agent=3
```

**Ket qua quan sat:**
- 3 container `agent_1`, `agent_2`, `agent_3` duoc start.
- Nginx round-robin requests giua 3 instances.
- Response co field `"served_by": "instance-abc123"` cho thay instance khac nhau.

```bash
# Goi 10 requests
for i in $(seq 1 10); do
  curl -s http://localhost/chat -X POST \
    -H "Content-Type: application/json" \
    -d '{"question":"Hi"}' | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('served_by','?'))"
done

# Ket qua: instance-abc, instance-def, instance-ghi, ... (round-robin)
```

### Exercise 5.5: Test stateless

```bash
python 05-scaling-reliability/production/test_stateless.py
```

Script kiem tra:
1. Tao session, gui 3 messages → kiem tra history duoc luu.
2. Goi `/chat/{session_id}/history` tu instance khac → lich su van con.
3. Neu Redis hoat dong: tat 1 container, gui request tiep → con conversation.
4. Neu in-memory: tat container → mat conversation.

**Ket qua mong doi voi Redis**: `PASS — history preserved across instances`.

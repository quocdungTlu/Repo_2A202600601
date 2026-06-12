# MediLich — Production AI Agent (Lab 12 Complete)

Quét đơn thuốc → OCR → AI parse → Validate → Lịch uống thuốc tự động.
Kết hợp **tất cả** Day 12 concepts vào một project hoàn chỉnh.

## Checklist Deliverable

- [x] Dockerfile (multi-stage, < 500 MB)
- [x] docker-compose.yml (agent + redis)
- [x] .dockerignore
- [x] Health check endpoint (`GET /health`)
- [x] Readiness endpoint (`GET /ready`)
- [x] API Key authentication
- [x] Rate limiting
- [x] Cost guard
- [x] Config từ environment variables
- [x] Structured logging
- [x] Graceful shutdown
- [x] Public URL ready (Railway / Render config)

---

## Cấu Trúc

```
06-lab-complete/
├── app/
│   ├── main.py         # Entry point — MediLich endpoints
│   └── config.py       # 12-factor config
├── utils/
│   ├── mock_llm.py     # Parse đơn thuốc (mock + OpenAI)
│   ├── ocr.py          # VietOCR client (mock fallback)
│   ├── parse_rx.py     # Validate drug schedule
│   └── schedule_rx.py  # Build lịch uống thuốc
├── Dockerfile          # Multi-stage, production-ready
├── docker-compose.yml  # Full stack
├── railway.toml        # Deploy Railway
├── render.yaml         # Deploy Render
├── .env.example        # Template
├── .dockerignore
└── requirements.txt
```

---

## Endpoints

| Method | Path | Auth | Mô tả |
|--------|------|------|-------|
| GET | `/` | — | App info |
| POST | `/scan` | X-API-Key | Upload ảnh đơn thuốc → lịch |
| POST | `/parse` | X-API-Key | Nhập text đơn thuốc → lịch |
| GET | `/health` | — | Liveness probe |
| GET | `/ready` | — | Readiness probe |
| GET | `/metrics` | X-API-Key | Basic metrics |

---

## Chạy Local

```bash
# 1. Setup
cp .env.example .env

# 2. Chạy với Docker Compose
docker compose up

# 3. Test health
curl http://localhost:8000/health

# 4. Parse đơn thuốc (mock, không cần API key thật)
curl -X POST http://localhost:8000/parse \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"raw_text": "Amoxicillin 500mg 1 viên x 3 lần/ngày sau ăn 7 ngày"}'

# 5. Scan ảnh
curl -X POST http://localhost:8000/scan \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -F "image=@prescription.jpg"
```

---

## Deploy Railway (< 5 phút)

```bash
npm i -g @railway/cli
railway login
railway init
railway variables set OPENAI_API_KEY=sk-...
railway variables set AGENT_API_KEY=your-secret-key
railway up
railway domain
```

---

## Deploy Render

1. Push repo lên GitHub
2. Render Dashboard → New → Blueprint
3. Connect repo → Render đọc `render.yaml`
4. Set secrets: `OPENAI_API_KEY`, `AGENT_API_KEY`
5. Deploy → Nhận URL!

---

## Kiểm Tra Production Readiness

```bash
python check_production_ready.py
```

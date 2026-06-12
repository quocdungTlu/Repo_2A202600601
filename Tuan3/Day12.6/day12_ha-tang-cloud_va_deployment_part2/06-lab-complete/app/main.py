"""
MediLich — Production AI Agent
Quét đơn thuốc → OCR → Parse → Validate → Lịch uống thuốc

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_and_record_cost, get_daily_cost
from utils.mock_llm import parse_rx_text
from utils.ocr import ocr_image
from utils.parse_rx import validate_lines, has_blocking_issues, lines_from_llm_response
from utils.schedule_rx import build_schedule, group_by_date

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Quét đơn thuốc → Lịch uống thuốc tự động",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.pop("server", None)
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class ParseRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, max_length=4000,
                          description="Raw text từ đơn thuốc (OCR output hoặc nhập tay)")
    start_date: str | None = Field(None, description="Ngày bắt đầu uống thuốc (YYYY-MM-DD)")

class RxLine(BaseModel):
    drug_name: str
    dose_per_time: str
    frequency_per_day: int
    meal_relation: str
    duration_days: int
    confidence: dict

class ScanResponse(BaseModel):
    ocr_text: str
    lines: list[RxLine]
    issues: list[dict]
    has_blocking_issues: bool
    schedule: list[dict]
    schedule_by_date: dict[str, list[dict]]
    model: str
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "description": "Quét đơn thuốc → Lịch uống thuốc tự động",
        "endpoints": {
            "scan": "POST /scan (upload ảnh đơn thuốc, requires X-API-Key)",
            "parse": "POST /parse (nhập text đơn thuốc, requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/scan", response_model=ScanResponse, tags=["MediLich"])
async def scan_prescription(
    request: Request,
    image: UploadFile = File(..., description="Ảnh đơn thuốc (jpg/png)"),
    start_date: str | None = None,
    _key: str = Depends(verify_api_key),
):
    """
    Upload ảnh đơn thuốc → OCR → Parse → Validate → Lịch uống thuốc.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    check_rate_limit(_key[:8])

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 10 MB)")

    logger.info(json.dumps({
        "event": "scan_start",
        "filename": image.filename,
        "size_bytes": len(image_bytes),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # OCR
    ocr_text = ocr_image(image_bytes, settings.vietocr_url)

    # Budget check (estimate tokens)
    input_tokens = len(ocr_text.split()) * 2
    check_and_record_cost(input_tokens, 0)

    # LLM parse
    parsed = parse_rx_text(ocr_text, settings.openai_api_key, settings.llm_model)
    lines = lines_from_llm_response(parsed)

    output_tokens = len(str(parsed)) // 4
    check_and_record_cost(0, output_tokens)

    # Validate
    issues = validate_lines(lines)
    blocking = has_blocking_issues(issues)

    # Build schedule
    from datetime import date
    sd = None
    if start_date:
        try:
            sd = date.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(400, f"start_date không hợp lệ: {start_date} (cần YYYY-MM-DD)")

    schedule = build_schedule(lines, sd)
    by_date = group_by_date(schedule)

    logger.info(json.dumps({
        "event": "scan_done",
        "drug_count": len(lines),
        "issues": len(issues),
        "blocking": blocking,
        "schedule_events": len(schedule),
    }))

    return ScanResponse(
        ocr_text=ocr_text,
        lines=lines,
        issues=issues,
        has_blocking_issues=blocking,
        schedule=schedule,
        schedule_by_date=by_date,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/parse", response_model=ScanResponse, tags=["MediLich"])
async def parse_prescription(
    body: ParseRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Nhập thủ công text đơn thuốc → Parse → Validate → Lịch uống thuốc.
    Dùng khi không có ảnh hoặc muốn test nhanh.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    check_rate_limit(_key[:8])

    input_tokens = len(body.raw_text.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(json.dumps({
        "event": "parse_start",
        "text_len": len(body.raw_text),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    parsed = parse_rx_text(body.raw_text, settings.openai_api_key, settings.llm_model)
    lines = lines_from_llm_response(parsed)

    output_tokens = len(str(parsed)) // 4
    check_and_record_cost(0, output_tokens)

    issues = validate_lines(lines)
    blocking = has_blocking_issues(issues)

    from datetime import date
    sd = None
    if body.start_date:
        try:
            sd = date.fromisoformat(body.start_date)
        except ValueError:
            raise HTTPException(400, f"start_date không hợp lệ: {body.start_date}")

    schedule = build_schedule(lines, sd)
    by_date = group_by_date(schedule)

    return ScanResponse(
        ocr_text=body.raw_text,
        lines=lines,
        issues=issues,
        has_blocking_issues=blocking,
        schedule=schedule,
        schedule_by_date=by_date,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    checks = {
        "llm": "mock" if not settings.openai_api_key else "openai",
        "ocr": "mock" if "localhost" in settings.vietocr_url else "vietocr",
    }
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    cost = get_daily_cost()
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(cost / settings.daily_budget_usd * 100, 1),
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )

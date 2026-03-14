"""
CoastCapital Platform — FastAPI service for MCP dispatch + Architecture Agent.

Endpoints:
  POST /api/classify-intent      — Ollama-powered Slack text -> N8N workflow mapping
  POST /api/architecture-audit   — Trigger codebase quality audit
  POST /api/predictions/{id}/vote — Submit feedback on a prediction
  GET  /api/predictions          — List predictions for feedback dashboard
  GET  /api/predictions/stats    — Aggregate accuracy stats
  GET  /api/intents              — List all available intents
  GET  /dashboard                — Feedback dashboard (HTML)
  GET  /health                   — Liveness probe
"""

import json
import os
import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import uuid as _uuid

from app.config import Config
from app.dispatcher import classify_intent, get_intent_registry

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger("platform")


# -- Lifespan -----------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Platform service starting -- Ollama at %s", Config.OLLAMA_BASE_URL)
    # Initialize MySQL table on startup (non-blocking)
    try:
        from app.db import init_db
        init_db()
    except Exception as exc:
        logger.warning("DB init deferred (MySQL may not be ready): %s", exc)
    yield
    logger.info("Platform service shutting down")


app = FastAPI(
    title="CoastCapital Platform",
    version="1.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def _add_request_id(request: Request, call_next):
    """Add X-Request-ID header to all responses."""
    rid = request.headers.get("X-Request-ID", _uuid.uuid4().hex[:8])
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

# -- Static files & templates -------------------------------------------------

_app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_app_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(_app_dir / "templates"))


# -- Auth ---------------------------------------------------------------------

def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key. Denies all requests if PLATFORM_API_KEY is not set."""
    if not Config.PLATFORM_API_KEY or x_api_key != Config.PLATFORM_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_api_key


# -- Request / Response Models ------------------------------------------------

class ClassifyRequest(BaseModel):
    text: str
    source: str = "slack"


class ClassifyResponse(BaseModel):
    intent: str
    params: dict[str, Any]
    confidence: float
    clarification: str | None
    webhook_path: str | None
    prediction_id: int | None = None


class AuditRequest(BaseModel):
    modules: list[str] | None = None
    dry_run: bool = False


class VoteRequest(BaseModel):
    vote: str  # "up" or "down"
    correct_intent: str | None = None
    note: str | None = None


# -- HTML Routes --------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "active_page": "dispatcher",
        "ollama_model": Config.OLLAMA_MODEL,
        "intents_json": json.dumps(get_intent_registry()),
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "active_page": "dispatcher",
        "ollama_model": Config.OLLAMA_MODEL,
        "intents_json": json.dumps(get_intent_registry()),
    })


# -- API Routes ---------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "coastcapital-platform", "ts": datetime.now(timezone.utc).isoformat()}


@app.post("/api/classify-intent", response_model=ClassifyResponse)
async def api_classify_intent(req: ClassifyRequest, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    logger.info("Classifying intent -- source=%s text=%s", req.source, req.text[:80])

    start = time.monotonic()
    result = classify_intent(req.text)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        "Classification complete -- intent=%s confidence=%.2f elapsed=%dms",
        result.intent, result.confidence, elapsed_ms,
    )

    # Log prediction to MySQL
    prediction_id = None
    try:
        from app.db import log_prediction
        prediction_id = log_prediction(
            source=req.source,
            user_text=req.text,
            predicted_intent=result.intent,
            predicted_params=result.params,
            confidence=result.confidence,
            ollama_model=Config.OLLAMA_MODEL,
            response_time_ms=elapsed_ms,
            webhook_path=result.webhook_path,
        )
    except Exception as exc:
        logger.warning("Prediction logging failed (non-blocking): %s", exc)

    return ClassifyResponse(
        **result.to_dict(),
        prediction_id=prediction_id,
    )


@app.get("/api/intents")
async def api_intents(x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    return {"intents": get_intent_registry()}


@app.post("/api/architecture-audit")
async def api_architecture_audit(req: AuditRequest, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    logger.info("Architecture audit requested -- modules=%s dry_run=%s", req.modules, req.dry_run)

    from app.agents.architecture_agent import run_audit

    findings = await run_audit(
        workspace_root=Config.WORKSPACE_ROOT,
        modules=req.modules,
        dry_run=req.dry_run,
    )

    logger.info("Audit complete -- %d findings", len(findings))
    return {"findings": findings, "count": len(findings), "ts": datetime.now(timezone.utc).isoformat()}


# -- Prediction Feedback API --------------------------------------------------

@app.get("/api/predictions")
async def api_get_predictions(
    limit: int = 50,
    offset: int = 0,
    vote: str | None = None,
    _key: str = Depends(verify_api_key),
):
    """List recent predictions for the feedback dashboard."""
    from app.db import get_predictions
    rows = get_predictions(limit=limit, offset=offset, vote_filter=vote)
    # Serialize datetime objects
    for row in rows:
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()
    return {"predictions": rows}


@app.get("/api/predictions/stats")
async def api_prediction_stats(_key: str = Depends(verify_api_key)):
    """Aggregate prediction accuracy stats."""
    from app.db import get_stats
    from decimal import Decimal
    stats = get_stats()
    # Convert Decimal types to float for JSON serialization
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in stats.items()}


@app.post("/api/predictions/{prediction_id}/vote")
async def api_vote(prediction_id: int, req: VoteRequest, _key: str = Depends(verify_api_key)):
    """Submit an upvote or downvote on a prediction."""
    if req.vote not in ("up", "down"):
        raise HTTPException(status_code=400, detail="vote must be 'up' or 'down'")

    from app.db import submit_vote
    ok = submit_vote(
        prediction_id=prediction_id,
        vote=req.vote,
        correct_intent=req.correct_intent,
        note=req.note,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return {"ok": True, "prediction_id": prediction_id, "vote": req.vote}

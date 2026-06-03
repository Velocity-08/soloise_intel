"""
Soloise Intel API — Vercel Entry Point
FastAPI wrapped with Mangum for serverless deployment.
"""

import os
import sys
import time
import uuid
import logging
import asyncio
import traceback

# Ensure the api/ directory is on the path so all local modules resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from stages.dataset_loader import load_dataset, get_dataset_stats
from pipeline import run_pipeline
from gateway.auth import validate_api_key
from gateway.credits import check_and_deduct_credit
from gateway.logger import log_usage
from gateway.models import RecommendRequest, RecommendResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
log = logging.getLogger("soloise")

# ── Dataset loaded once at cold start ────────────────────────────────────────
try:
    load_dataset()
    log.info("[BOOT] Dataset loaded into memory")
except Exception as e:
    log.error(f"[BOOT] Dataset load failed: {e}")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Soloise Behavioural Intelligence API",
    description=(
        "Send any text, get ranked behavioural principles.\n\n"
        "**Authentication:** `Authorization: Bearer sk-sol-<your_key>`\n\n"
        "Get your API key at https://soloise.com/dashboard"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Get ranked behavioural principles",
    responses={
        200: {"description": "Principles returned successfully"},
        401: {"description": "Invalid or missing API key"},
        402: {"description": "No credits remaining"},
        422: {"description": "Invalid request body"},
        500: {"description": "Internal pipeline error"},
    },
)
async def recommend(
    body: RecommendRequest,
    key_row: dict = Depends(validate_api_key),
):
    request_id = str(uuid.uuid4())
    user_id = key_row["user_id"]
    key_id = key_row["id"]
    t_start = time.monotonic()

    log.info(f"[{request_id[:8]}] /recommend — user={user_id[:8]}")

    try:
        credits_remaining, credits_used = await check_and_deduct_credit(user_id, len(body.query))
    except Exception as e:
        log.error(f"[{request_id[:8]}] Credit check failed: {str(e)}")
        return JSONResponse(status_code=402, content={
            "success": False, 
            "request_id": request_id,
            "error": {"type": "credit_error", "message": str(e)}
        })

    try:
        principles = await asyncio.to_thread(
            run_pipeline,
            raw_input=body.query,
            top_n=body.top_n,
            debug=False,
        )
    except Exception as e:
        error_details = traceback.format_exc()
        log.error(f"[{request_id[:8]}] Pipeline failed: {str(e)}\n{error_details}")
        
        asyncio.create_task(log_usage(
            user_id=user_id, key_id=key_id,
            query_length=len(body.query), top_n=body.top_n,
            latency_ms=int((time.monotonic() - t_start) * 1000), success=False,
        ))
        
        return JSONResponse(status_code=500, content={
            "success": False, 
            "request_id": request_id,
            "error": {"type": "pipeline_error", "message": str(e)}
        })

    latency_ms = int((time.monotonic() - t_start) * 1000)
    log.info(f"[{request_id[:8]}] Done — {len(principles)} results in {latency_ms}ms")

    asyncio.create_task(log_usage(
        user_id=user_id, key_id=key_id,
        query_length=len(body.query), top_n=body.top_n,
        latency_ms=latency_ms, success=True,
    ))

    return RecommendResponse(
        request_id=request_id,
        results=principles,
        count=len(principles),
        credits_used=credits_used,
        credits_remaining=credits_remaining,
        latency_ms=latency_ms,
    )


@app.get("/health", summary="Health check")
async def health():
    try:
        stats = get_dataset_stats()
        return {"status": "ok", "dataset": stats}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


@app.get("/", summary="API info", include_in_schema=False)
async def root():
    return {
        "name": "Soloise Behavioural Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "POST /recommend": "Get ranked principles. Requires Bearer token.",
            "GET /health": "Health check + dataset stats.",
        },
    }


# ── Mangum handler (Vercel / AWS Lambda adapter) ─────────────────────────────
handler = Mangum(app, lifespan="off")
"""
Soloise Gateway — app.py
Public FastAPI server with token-minimized Kimi reranking.
"""

import os
import time
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Import from parent package
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import run_pipeline
from stages.dataset_loader import load_dataset, get_dataset_stats
from gateway.auth import validate_api_key
from gateway.credits import check_and_deduct_credit
from gateway.logger import log_usage
from gateway.models import RecommendRequest, RecommendResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
)
log = logging.getLogger("soloise.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Loading dataset into memory...")
    load_dataset()
    log.info("Dataset ready. Gateway is live.")
    yield
    log.info("Gateway shutting down.")


app = FastAPI(
    title="Soloise Behavioural Intelligence API",
    description=(
        "POST /recommend — send any text, get ranked behavioural principles.\n\n"
        "Authentication: `Authorization: Bearer sk-sol-<your_key>`\n\n"
        "Get your API key at https://soloise.com/dashboard"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("DASHBOARD_URL", "https://soloise.com"),
        "http://localhost:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Get ranked behavioural principles for any input",
    responses={
        200: {"description": "Principles returned successfully"},
        401: {"description": "Invalid or missing API key"},
        402: {"description": "No credits remaining"},
        422: {"description": "Invalid request body"},
        500: {"description": "Internal pipeline error"},
    }
)
async def recommend(
    body: RecommendRequest,
    background: BackgroundTasks,
    key_row: dict = Depends(validate_api_key),
):
    user_id = key_row["user_id"]
    key_id = key_row["id"]
    t_start = time.monotonic()

    credits_remaining, credits_used = await check_and_deduct_credit(user_id, len(body.query))

    try:
        principles = await asyncio.to_thread(
            run_pipeline,
            raw_input=body.query,
            top_n=body.top_n,
            debug=False,
        )
    except ValueError as e:
        background.add_task(
            log_usage,
            user_id=user_id,
            key_id=key_id,
            query_length=len(body.query),
            top_n=body.top_n,
            latency_ms=int((time.monotonic() - t_start) * 1000),
            success=False,
        )
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e), "code": "BAD_INPUT"},
        )
    except RuntimeError as e:
        background.add_task(
            log_usage,
            user_id=user_id,
            key_id=key_id,
            query_length=len(body.query),
            top_n=body.top_n,
            latency_ms=int((time.monotonic() - t_start) * 1000),
            success=False,
        )
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": str(e), "code": "UPSTREAM_ERROR"},
        )
    except Exception:
        log.exception("Unexpected pipeline error")
        background.add_task(
            log_usage,
            user_id=user_id,
            key_id=key_id,
            query_length=len(body.query),
            top_n=body.top_n,
            latency_ms=int((time.monotonic() - t_start) * 1000),
            success=False,
        )
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal error.", "code": "INTERNAL_ERROR"},
        )

    latency_ms = int((time.monotonic() - t_start) * 1000)
    log.info(f"[{user_id[:8]}…] /recommend → {len(principles)} results in {latency_ms}ms")

    background.add_task(
        log_usage,
        user_id=user_id,
        key_id=key_id,
        query_length=len(body.query),
        top_n=body.top_n,
        latency_ms=latency_ms,
        success=True,
    )

    return RecommendResponse(
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "gateway.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level="info",
    )

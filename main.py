import time
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from pipeline import run_pipeline
from stages.dataset_loader import load_dataset, get_dataset_stats
from gateway.logger import logger

app = FastAPI(
    title="Soloise Intel API",
    description="Behavioral intelligence retrieval API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    load_dataset()
    logger.info("[BOOT] Dataset loaded into memory")

class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Raw user query")
    top_n: Optional[int] = Field(default=5, ge=1, le=20)
    debug: Optional[bool] = False

class ErrorResponse(BaseModel):
    type: str
    message: str

class RecommendResponse(BaseModel):
    success: bool
    request_id: str
    query: str
    count: int
    latency_ms: float
    results: List[Dict[str, Any]]

@app.post("/v1/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest):
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    logger.info(f"Request started | {request_id}")

    try:
        results = run_pipeline(
            raw_input=request.query,
            top_n=request.top_n,
            debug=request.debug,
        )

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(f"Request completed | {request_id} | {latency_ms}ms")

        return {
            "success": True,
            "request_id": request_id,
            "query": request.query,
            "count": len(results),
            "latency_ms": latency_ms,
            "results": results,
        }

    except ValueError as e:
        logger.error(f"Request failed | {request_id} | {str(e)}")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "request_id": request_id,
                "error": {"type": "validation_error", "message": str(e)},
            },
        )

    except RuntimeError as e:
        logger.error(f"Request failed | {request_id} | {str(e)}")
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "request_id": request_id,
                "error": {"type": "upstream_error", "message": str(e)},
            },
        )

    except Exception as e:
        logger.error(f"Request failed | {request_id} | {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "request_id": request_id,
                "error": {"type": "internal_error", "message": str(e)},
            },
        )

@app.get("/health")
async def health():
    stats = get_dataset_stats()
    return {"status": "healthy", "dataset": stats}

@app.get("/")
async def root():
    return {
        "name": "Soloise Intel API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoint": "/v1/recommend",
    }

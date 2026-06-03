"""
Gateway Models
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any


class RecommendRequest(BaseModel):
    query: str = Field(
        ...,
        description="Any input: plain text, JSON, CSV, tokens, multi-line. 1–1000 chars.",
        min_length=1,
    )
    top_n: Optional[int] = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of principles to return (1–20). Default: 5.",
    )


class RecommendResponse(BaseModel):
    success: bool = True
    request_id: str
    results: List[Any]
    count: int
    credits_used: int
    credits_remaining: int
    latency_ms: int


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    code: str

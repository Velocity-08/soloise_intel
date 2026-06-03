"""
Logger — async fire-and-forget usage logging to Supabase.
"""

import logging
from datetime import datetime, timezone
from gateway.auth import get_supabase

logger = logging.getLogger("soloise.usage")


async def log_usage(
    user_id: str,
    key_id: str,
    query_length: int,
    top_n: int,
    latency_ms: int,
    success: bool = True,
) -> None:
    try:
        supabase = get_supabase()
        supabase.table("usage_logs").insert({
            "user_id": user_id,
            "key_id": key_id,
            "query_length": query_length,
            "top_n": top_n,
            "latency_ms": latency_ms,
            "success": success,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"Usage logging failed (non-fatal): {e}")

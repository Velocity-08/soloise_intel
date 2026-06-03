"""
Credits — check and deduct credits per request.
"""

import os
from fastapi import HTTPException
from supabase import create_client, Client

_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _supabase


async def check_and_deduct_credit(user_id: str, query_length: int) -> tuple[int, int]:
    """
    Returns (credits_remaining, credits_used).
    Raises HTTP 402 if the user has no credits.
    """
    supabase = _get_supabase()
    cost = max(1, query_length // 100)

    try:
        response = (
            supabase.rpc(
                "deduct_credit",
                {"p_user_id": user_id, "p_amount": cost},
            )
            .execute()
        )
    except Exception as e:
        error_msg = str(e)
        if "INSUFFICIENT_CREDITS" in error_msg:
            raise HTTPException(
                status_code=402,
                detail={"error": "Insufficient credits.", "code": "INSUFFICIENT_CREDITS"},
            )
        raise HTTPException(
            status_code=500,
            detail={"error": "Credit check failed. Please try again.", "code": "CREDIT_ERROR"},
        )

    data = response.data
    if data is None or (isinstance(data, dict) and data.get("error")):
        raise HTTPException(
            status_code=402,
            detail={"error": "Insufficient credits.", "code": "INSUFFICIENT_CREDITS"},
        )

    remaining = data if isinstance(data, int) else data.get("credits_remaining", 0)
    return remaining, cost


async def get_balance(user_id: str) -> int:
    supabase = _get_supabase()
    response = (
        supabase.table("credit_balances")
        .select("credits")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not response.data:
        return 0
    return response.data["credits"]
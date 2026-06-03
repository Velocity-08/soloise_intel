"""
Credits
Atomically deduct credits based on query size using Supabase RPC.
"""

from fastapi import HTTPException
from .auth import get_supabase


def calculate_credit_cost(query_length: int) -> int:
    """
    Internal only — never exposed to users.
    Based on character length as proxy for token size.
    ~4 chars per token is standard approximation.
    """
    if query_length < 20_000:      # ~5k tokens
        return 5
    elif query_length < 60_000:    # ~15k tokens
        return 10
    else:                           # up to ~30k tokens
        return 20


async def check_and_deduct_credit(user_id: str, query_length: int) -> tuple[int, int]:
    """
    Returns (credits_remaining, credits_used).
    """
    supabase = get_supabase()
    cost = calculate_credit_cost(query_length)

    try:
        response = supabase.rpc(
            "deduct_credit",
            {"p_user_id": user_id, "p_amount": cost}
        ).execute()
    except Exception as e:
        error_msg = str(e)

        if "INSUFFICIENT_CREDITS" in error_msg:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "You have no credits remaining. Contact us to top up.",
                    "code": "NO_CREDITS",
                },
            )

        raise HTTPException(
            status_code=500,
            detail={"error": "Credit check failed. Please try again.", "code": "CREDIT_ERROR"},
        )

    return response.data, cost


async def get_balance(user_id: str) -> int:
    supabase = get_supabase()

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

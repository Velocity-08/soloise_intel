"""
Auth — validates the Bearer API key on every request.
"""

import hashlib
import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _supabase = create_client(url, key)
    return _supabase


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


bearer_scheme = HTTPBearer(auto_error=False)


async def validate_api_key(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing API key. Send: Authorization: Bearer <key>", "code": "MISSING_KEY"},
        )

    raw_key = credentials.credentials

    if not raw_key.startswith("sk-sol-"):
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid API key format.", "code": "INVALID_KEY_FORMAT"},
        )

    key_hash = hash_key(raw_key)
    supabase = get_supabase()

    try:
        response = (
            supabase.table("api_keys")
            .select("id, user_id, is_active")
            .eq("key_hash", key_hash)
            .single()
            .execute()
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid API key.", "code": "INVALID_KEY"},
        )

    if not response.data:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid API key.", "code": "INVALID_KEY"},
        )

    if not response.data.get("is_active"):
        raise HTTPException(
            status_code=401,
            detail={"error": "API key is disabled.", "code": "KEY_DISABLED"},
        )

    return response.data

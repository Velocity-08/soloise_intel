"""
Auth — validates the Bearer API key on every request.

REFACTOR (this revision):
Pulled the actual "given a raw key string, return the key row or raise 401"
logic out of validate_api_key into a standalone lookup_key() function.
validate_api_key (used by /recommend and as the default /mcp dependency)
just extracts the raw key from the Authorization header and calls lookup_key().

Why: Claude's MCP connector UI (the simple "paste a URL" flow) has no field
for entering a Bearer token — it only takes a URL. So for /mcp specifically,
the API key has to travel as the trailing path segment instead of a header
(see api/index.py mcp_handler). Both paths now validate through the exact
same lookup_key() — same hash, same Supabase query, same is_active check —
so there's one source of truth for "is this a valid, active key" regardless
of whether it arrived via header or path.
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


def lookup_key(raw_key: str) -> dict:
    """
    Validate a raw API key string and return its api_keys row.
    Raises HTTPException(401) on any failure. This is the single source of
    truth for key validation — both header-based and path-based auth call
    this, so there is exactly one place that defines what a "valid key" is.
    """
    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing API key. Send: Authorization: Bearer <key>", "code": "MISSING_KEY"},
        )

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


bearer_scheme = HTTPBearer(auto_error=False)


async def validate_api_key(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """
    Header-based auth dependency, used by /recommend and as the default
    auth path for /mcp. Extracts the raw key from the Authorization header
    and delegates to lookup_key() for the actual validation.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing API key. Send: Authorization: Bearer <key>", "code": "MISSING_KEY"},
        )

    return lookup_key(credentials.credentials)
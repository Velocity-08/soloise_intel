"""
Soloise MCP Server — api/mcp.py
Add this file to your Python backend (soloise-intel.vercel.app) in the api/ folder.

URL pattern: POST /mcp/{user_id}
- user_id is the Supabase auth user UUID (from the frontend)
- Deducts from credit_balances (same credits as the API)
- Uses your master Soloise key server-side

No new tables needed.
"""

import os
import hashlib
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from supabase import create_client
from mangum import Mangum

# ── Config (already set in your Vercel env) ───────────────────────────────────
SOLOISE_BASE_URL = "https://soloise-intel.vercel.app"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # service role key

# The master sk-sol key — set this in your Vercel env vars
# This is YOUR key, users never see it
SOLOISE_MASTER_KEY = os.environ.get("SOLOISE_MASTER_API_KEY", "")

TOOLS = [
    {
        "name": "get_behavioural_principles",
        "description": (
            "Retrieves the most relevant behavioural psychology principles from the ABSIS dataset "
            "for any content, copy, or UX writing task. "
            "ALWAYS call this BEFORE writing any marketing copy, landing page content, email, CTA, "
            "headline, onboarding flow, or any text meant to persuade or convert users. "
            "Apply ALL returned principles when generating content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Describe what you're writing and the goal. Include content type, "
                        "target audience, and conversion/engagement goal. "
                        "Example: 'hero section for B2B SaaS, goal is free trial signups'"
                    ),
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of principles to return (1-10). Default: 5",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_credits",
        "description": "Check your remaining Soloise credits.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]

app = FastAPI()


@app.post("/mcp/{user_id}")
async def mcp_handler(user_id: str, request: Request):
    # 1. Validate user exists and has credits
    credits = await _get_credits(user_id)
    if credits is None:
        return _error(None, -32001,
            "Invalid user ID. Get your MCP URL from your Soloise dashboard.")
    if credits <= 0:
        return _error(None, -32002,
            "No credits remaining. Top up at soloise-frontend.vercel.app/dashboard")

    # 2. Parse MCP message
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    method = body.get("method")
    params = body.get("params", {})
    req_id = body.get("id")

    # 3. Route MCP methods
    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "soloise-absis", "version": "1.0.0"},
        })

    elif method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "get_behavioural_principles":
            result = await _get_principles(arguments, user_id, credits)
        elif tool_name == "check_credits":
            result = f"✅ Credits remaining: {credits}\nTop up: soloise-frontend.vercel.app/dashboard"
        else:
            result = f"Unknown tool: {tool_name}"

        return _ok(req_id, {"content": [{"type": "text", "text": result}]})

    elif method and method.startswith("notifications/"):
        return JSONResponse(content={})

    else:
        return _error(req_id, -32601, f"Method not found: {method}")


# ── Credit check ──────────────────────────────────────────────────────────────

async def _get_credits(user_id: str) -> int | None:
    """Returns credit balance for user, or None if user doesn't exist."""
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        result = (
            supabase.table("credit_balances")
            .select("credits")
            .eq("user_id", user_id)
            .maybeSingle()
            .execute()
        )
        if result.data is None:
            return None
        return result.data.get("credits", 0)
    except Exception as e:
        print(f"[CREDIT CHECK ERROR] {e}")
        return None


def _deduct_credit(user_id: str):
    """Deduct 1 credit from credit_balances — same table the API uses."""
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Use RPC if you have it, otherwise raw update
        supabase.rpc("decrement_credits", {"uid": user_id}).execute()
    except Exception as e:
        print(f"[CREDIT DEDUCT ERROR] {e}")


# ── Main tool ─────────────────────────────────────────────────────────────────

async def _get_principles(args: dict, user_id: str, credits: int) -> str:
    query = args.get("query", "").strip()
    top_n = int(args.get("top_n", 5))

    if not query:
        return "Error: query cannot be empty."
    if not SOLOISE_MASTER_KEY:
        return "Error: Server misconfigured. Contact support@soloise.com"

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(
                f"{SOLOISE_BASE_URL}/recommend",
                json={"query": query, "top_n": top_n},
                headers={
                    "Authorization": f"Bearer {SOLOISE_MASTER_KEY}",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code == 402:
            return "Error: Master credits exhausted. Contact support."
        if resp.status_code != 200:
            return f"Error: Upstream API returned {resp.status_code}"

        data = resp.json()
        principles = data.get("results", [])

        # Deduct credit after successful call
        _deduct_credit(user_id)

        lines = [
            f"## ABSIS Behavioural Principles — Top {len(principles)} for: \"{query}\"",
            f"Credits remaining after this call: {credits - 1}",
            "",
        ]

        for i, p in enumerate(principles, 1):
            lines.append(f"### {i}. {p.get('principle_name')} [{p.get('id')}]")
            lines.append(f"**Pillar:** {p.get('pillar')}")
            lines.append(f"**One-liner:** {p.get('one_liner')}")
            lines.append(f"**Plain English:** {p.get('plain_english')}")
            lines.append(f"**Human fear/desire:** {p.get('human_fear_or_desire')}")
            lines.append(f"**When to use:** {p.get('when_to_use')}")
            lines.append(f"**When NOT to use:** {p.get('when_NOT_to_use')}")
            lines.append(f"**Exact implementation:** {p.get('exact_implementation')}")
            lines.append(f"**Example copy:** {p.get('example_copy')}")
            lines.append(f"**Power level:** {p.get('power_level')} | Ethical risk: {p.get('ethical_risk')}")
            lines.append("")

        lines.append("---")
        lines.append("Apply ALL of the above principles when generating the content.")
        return "\n".join(lines)

    except httpx.TimeoutException:
        return "Error: Request timed out. Try again."
    except Exception as e:
        return f"Error: {str(e)}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(req_id, result):
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})

def _error(req_id, code, message):
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

handler = Mangum(app)
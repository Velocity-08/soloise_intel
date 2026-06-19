"""
Soloise Intel API — Vercel Entry Point
FastAPI wrapped with Mangum for serverless deployment.

NOTE: vercel.json only builds api/index.py (see "builds" -> "src": "api/index.py").
That means this is the ONLY Python file Vercel turns into a serverless function.
api/mcp.py existed in the repo but was never deployed or routed to — every request,
including /mcp/{user_id} and /.well-known/..., was actually hitting THIS file.
api/mcp.py has been deleted; this file is the single source of truth for both
the REST API and the MCP server.

Also: deliberately NOT exposing /.well-known/oauth-protected-resource. Letting
that path 404 is what tells Claude's connector this server is authless. Serving
a 200 there with an empty authorization_servers list is what caused the original
"Couldn't register with sign-in service" error.

──────────────────────────────────────────────────────────────────────────────
MCP AUTH REDESIGN (this revision):
Previously /mcp/{user_id} trusted a bare path param as identity, then called
this API's own /recommend endpoint over HTTP using a shared SOLOISE_MASTER_KEY
— which meant every MCP call was paying for itself twice (once via the master
key's own credits inside /recommend, once via decrement_credits for the real
user) and had zero real authentication (anyone who guessed/saw a user_id could
spend that user's credits).

Now: /mcp requires the same `Authorization: Bearer sk-sol-...` that /recommend
requires, validated via the same validate_api_key() dependency. Once authed,
the handler calls run_pipeline() directly in-process (no self-HTTP-call, no
master key) and deducts credits via the same check_and_deduct_credit() that
/recommend uses — same cost formula, one credit ledger, one identity check.
──────────────────────────────────────────────────────────────────────────────
ROUTING FIX (this revision):
Claude's MCP connector calls the URL configured at connector-setup time, which
includes a per-connector UUID as a trailing path segment, e.g.
    POST /mcp/eb39351a-0abe-4492-b427-e0618df34586
The old routes were registered as exactly "/mcp" with no path param, so that
request matched no route for POST — it only structurally matched the
"/{path:path}" OPTIONS catch-all below, which doesn't allow POST. Starlette's
router sees a path match with no method match and returns 405 Method Not
Allowed, without ever entering the handler (confirmed via Vercel logs: 10ms
duration, "No outgoing requests").

Fix: both /mcp routes now also accept an optional trailing /{connector_id}
segment. connector_id is accepted but intentionally unused for auth/identity —
identity still comes entirely from validate_api_key (Authorization: Bearer
sk-sol-...), exactly as before. This means both of these now resolve to the
same handlers:
    POST /mcp
    POST /mcp/eb39351a-0abe-4492-b427-e0618df34586
──────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import time
import uuid
import logging
import asyncio
import traceback
from typing import Optional

# Ensure the api/ directory is on the path so all local modules resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Depends, Request
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

# ── Dataset loaded once at cold start ──────────────────────────────────────
try:
    load_dataset()
    log.info("[BOOT] Dataset loaded into memory")
except Exception as e:
    log.error(f"[BOOT] Dataset load failed: {e}")

# ── FastAPI app ─────────────────────────────────────────────────────────────
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

# Updated CORS for mobile and all devices
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://soloise-frontend.vercel.app",  # Your frontend
        "https://soloise-intel.vercel.app",     # Your backend
        "http://localhost:3000",                # Local frontend
        "http://localhost:8000",                # Local backend
        "https://*.vercel.app",                 # All Vercel apps
        "*"  # Allow all for now (remove in production if needed)
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],  # Allow all headers for mobile compatibility
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
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


# ══════════════════════════════════════════════════════════════════════════
# MCP server routes (Claude connector)
#
# Auth model: identical to /recommend. The Authorization: Bearer sk-sol-...
# header is required and validated via validate_api_key — same dependency,
# same api_keys table lookup, same is_active check. No user_id in the URL,
# no master key, no second credit ledger.
#
# Routing: both GET and POST accept either "/mcp" or "/mcp/{connector_id}".
# connector_id is accepted purely so Claude's connector URL (which includes
# a trailing UUID) resolves to a real route instead of 405ing. It is never
# used for identity or auth — see ROUTING FIX note at the top of this file.
# ══════════════════════════════════════════════════════════════════════════

MCP_TOOLS = [
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


@app.get("/mcp")
@app.get("/mcp/{connector_id}")
async def mcp_probe(connector_id: Optional[str] = None):
    """Claude sends a GET first to check if the server is alive. Must return 200, not 405."""
    return JSONResponse(content={"status": "ok", "server": "soloise-absis"})


@app.post("/mcp")
@app.post("/mcp/{connector_id}")
async def mcp_handler(
    request: Request,
    connector_id: Optional[str] = None,
    key_row: dict = Depends(validate_api_key),
):
    """
    Single MCP endpoint for all authenticated users.
    Identity comes entirely from validate_api_key (Authorization: Bearer sk-sol-...),
    exactly like /recommend. connector_id (if present in the URL) is accepted but
    unused — no user_id path param, no master key, no per-connector branching.
    """
    user_id = key_row["user_id"]
    key_id = key_row["id"]

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    method = body.get("method")
    params = body.get("params", {})
    req_id = body.get("id")

    if method == "initialize":
        return _mcp_ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "soloise-absis", "version": "1.0.0"},
        })

    elif method == "tools/list":
        return _mcp_ok(req_id, {"tools": MCP_TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "get_behavioural_principles":
            result = await _mcp_get_principles(arguments, user_id, key_id)
        elif tool_name == "check_credits":
            from gateway.credits import get_balance
            balance = await get_balance(user_id)
            result = f"✅ Credits remaining: {balance}\nTop up: soloise-frontend.vercel.app/dashboard"
        else:
            result = f"Unknown tool: {tool_name}"

        return _mcp_ok(req_id, {"content": [{"type": "text", "text": result}]})

    elif method and method.startswith("notifications/"):
        return JSONResponse(content={})

    else:
        return _mcp_error(req_id, -32601, f"Method not found: {method}")


async def _mcp_get_principles(args: dict, user_id: str, key_id: str) -> str:
    """
    Runs the same pipeline /recommend uses, in-process. Same credit check,
    same cost formula (max(1, len(query) // 100) via check_and_deduct_credit),
    same usage logging. No HTTP self-call, no master key.
    """
    query = args.get("query", "").strip()
    top_n = int(args.get("top_n", 5))

    if not query:
        return "Error: query cannot be empty."

    t_start = time.monotonic()

    try:
        credits_remaining, credits_used = await check_and_deduct_credit(user_id, len(query))
    except Exception as e:
        log.error(f"[MCP] Credit check failed for user={user_id[:8]}: {e}")
        if "INSUFFICIENT_CREDITS" in str(e):
            return "Error: No credits remaining. Top up at soloise-frontend.vercel.app/dashboard"
        return f"Error: Credit check failed: {str(e)}"

    try:
        principles = await asyncio.to_thread(
            run_pipeline,
            raw_input=query,
            top_n=top_n,
            debug=False,
        )
    except Exception as e:
        log.error(f"[MCP] Pipeline failed for user={user_id[:8]}: {e}\n{traceback.format_exc()}")
        asyncio.create_task(log_usage(
            user_id=user_id, key_id=key_id,
            query_length=len(query), top_n=top_n,
            latency_ms=int((time.monotonic() - t_start) * 1000), success=False,
        ))
        return f"Error: Pipeline failed: {str(e)}"

    latency_ms = int((time.monotonic() - t_start) * 1000)
    asyncio.create_task(log_usage(
        user_id=user_id, key_id=key_id,
        query_length=len(query), top_n=top_n,
        latency_ms=latency_ms, success=True,
    ))

    lines = [
        f"## ABSIS Behavioural Principles — Top {len(principles)} for: \"{query}\"",
        f"Credits used: {credits_used} | Credits remaining: {credits_remaining}",
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


def _mcp_ok(req_id, result):
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})


def _mcp_error(req_id, code, message):
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


# ══════════════════════════════════════════════════════════════════════════
# End MCP routes
# ══════════════════════════════════════════════════════════════════════════


@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle OPTIONS requests for CORS preflight"""
    return JSONResponse(
        status_code=200,
        content={"message": "OK"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "3600",
        }
    )


@app.get("/", summary="API info", include_in_schema=False)
async def root():
    return {
        "name": "Soloise Behavioural Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "POST /recommend": "Get ranked principles. Requires Bearer token.",
            "GET /health": "Health check + dataset stats.",
            "GET/POST /mcp": "MCP server endpoint for Claude connector. Requires Bearer token.",
            "GET/POST /mcp/{connector_id}": "Same as /mcp; connector_id is accepted but unused.",
        },
    }


# ── Mangum handler (Vercel / AWS Lambda adapter) ────────────────────────────
handler = Mangum(app, lifespan="off")
"""
STAGE 4 — Kimi K2.5 Semantic Re-rank via Fireworks AI
Minimized-output version.

Goals:
- Reduce completion tokens as much as possible.
- Keep only the 5 ranked principle IDs.
- Avoid breaking the pipeline if Fireworks rejects structured output.

Behavior:
- Primary path: structured JSON schema request (no reasoning output).
- Fallback path: plain JSON-only request if Fireworks returns 400/422.
- Final normalized output is always a bare JSON array string, so Stage 5
  can keep working unchanged.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
FIREWORKS_API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
MODEL = "accounts/fireworks/models/kimi-k2p5"

# Keep this short. The model only needs to choose IDs.
SYSTEM_PROMPT = (
    "You are a ranking engine. "
    "Return only the requested JSON. "
    "Do not explain your reasoning. "
    "Do not add markdown."
)


def _build_response_format() -> dict[str, Any]:
    """
    Fireworks structured output request.

    The docs say:
    - response_format can be {"type": "json_schema", "json_schema": {...}}
    - using json_schema disables reasoning output
    - schema should be included in the prompt too for best results
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "RankedIds",
            "schema": {
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "Principle ID such as P1-001"
                        },
                        "description": "Ranked principle IDs, best to worst."
                    }
                },
                "required": ["ids"],
                "additionalProperties": False
            }
        }
    }


def build_user_message(normalized_text: str, candidates: list, top_n: int) -> str:
    """
    Keep prompt compact. The reranker only needs lightweight descriptors.
    """
    compact_candidates = []
    for p in candidates:
        tags = p.get("metadata_tags", {})
        compact_candidates.append(
            {
                "id": p.get("id"),
                "principle_name": p.get("principle_name"),
                "one_liner": p.get("one_liner"),
                "use_case_keywords": tags.get("use_case_keywords", [])[:8],
                "funnel_stages": tags.get("funnel_stages", [])[:4],
                "goals": tags.get("goals", [])[:4],
            }
        )

    candidates_json = json.dumps(compact_candidates, ensure_ascii=False)

    return (
        f'User query:\n"""{normalized_text}"""\n\n'
        f"Candidate principles ({len(candidates)} total):\n"
        f"{candidates_json}\n\n"
        "Select the best principles for the query.\n"
        f"Return exactly {top_n} ranked IDs as JSON in this exact shape:\n"
        f'{{"ids":["P1-001","P1-002","P1-003","P1-004","P1-005"]}}\n'
        "No extra keys. No explanation. No markdown."
    )


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _extract_ordered_ids(text: str) -> list[str]:
    all_ids = re.findall(r"P\d+-\d+", text)
    return _dedupe_preserve_order(all_ids)


def _normalize_model_output(raw_output: str, top_n: int) -> str:
    """
    Convert any acceptable model output into a bare JSON array string.
    Stage 5 already understands JSON lists, so this keeps the pipeline stable.
    """
    text = (raw_output or "").strip()

    # Remove code fences if the model wrapped the JSON.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    # 1) Try direct JSON parse.
    try:
        parsed = json.loads(text)

        # {"ids": [...]} -> [...]
        if isinstance(parsed, dict) and isinstance(parsed.get("ids"), list):
            ids = [str(x) for x in parsed["ids"]]
            ids = [x for x in ids if re.fullmatch(r"P\d+-\d+", x)]
            ids = _dedupe_preserve_order(ids)
            return json.dumps(ids[:top_n])

        # [...] -> [...]
        if isinstance(parsed, list):
            ids = [str(x) for x in parsed]
            ids = [x for x in ids if re.fullmatch(r"P\d+-\d+", x)]
            ids = _dedupe_preserve_order(ids)
            return json.dumps(ids[:top_n])

    except Exception:
        pass

    # 2) Try FINAL RANKING line.
    final_match = re.search(
        r"FINAL RANKING[:\s]*(\[[^\]]*\])",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if final_match:
        try:
            parsed = json.loads(final_match.group(1))
            if isinstance(parsed, list):
                ids = [str(x) for x in parsed if re.fullmatch(r"P\d+-\d+", str(x))]
                ids = _dedupe_preserve_order(ids)
                if ids:
                    return json.dumps(ids[:top_n])
        except Exception:
            pass

    # 3) Last resort: regex extraction.
    ids = _extract_ordered_ids(text)
    return json.dumps(ids[:top_n])


def _post_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            FIREWORKS_API_URL,
            json=payload,
            headers=headers,
        )

    if response.status_code >= 400:
        # Include the response body in the exception so you can see the exact issue.
        raise RuntimeError(
            f"Fireworks request failed: HTTP {response.status_code} — {response.text}"
        )

    return response.json()


def rerank(
    normalized_text: str,
    candidates: list,
    dataset: list,  # kept for compatibility with existing pipeline signature
    top_n: int = 5,
) -> dict:
    """
    Stage 4 rerank.

    Returns:
        {
            "raw_output": "<JSON array string>",
            "candidates_sent": int,
            "model": str,
            "latency_ms": int,
            "usage": {...}
        }
    """
    if not FIREWORKS_API_KEY:
        raise ValueError(
            "FIREWORKS_API_KEY not found in environment. Check your .env file."
        )

    user_message = build_user_message(normalized_text, candidates, top_n)

    base_payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        # Very small output budget: we only need 5 IDs.
        "max_completion_tokens": 80,
        "temperature": 0.0,
        "top_k": 1,
        "n": 1,
        "stream": False,
        "raw_output": False,
        "perf_metrics_in_response": False,
    }

    # Primary path: structured output.
    structured_payload = dict(base_payload)
    structured_payload["response_format"] = _build_response_format()

    print("\n" + "=" * 80)
    print("[STAGE 4] Sending request to Kimi")
    print(f"[STAGE 4] Model: {MODEL}")
    print(f"[STAGE 4] Candidates: {len(candidates)}")
    print(f"[STAGE 4] top_n: {top_n}")
    print("=" * 80)

    start_time = time.time()
    data: dict[str, Any] | None = None
    used_fallback = False

    try:
        data = _post_chat_completion(structured_payload)
    except RuntimeError as e:
        err_text = str(e)

        # If Fireworks dislikes structured output on this model/config,
        # retry once without response_format but still keep the prompt strict.
        if "HTTP 400" in err_text or "HTTP 422" in err_text:
            print("[STAGE 4] Structured output rejected. Retrying without response_format...")
            used_fallback = True
            data = _post_chat_completion(base_payload)
        else:
            print("\n" + "=" * 80)
            print("[STAGE 4 ERROR]")
            print(err_text)
            print("=" * 80)
            raise RuntimeError(f"Stage 4 Kimi request failed: {err_text}") from e

    elapsed = round((time.time() - start_time) * 1000)

    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    print("\n" + "=" * 80)
    print("[KIMI TOKEN USAGE]")
    print(json.dumps(usage, indent=2))
    print("=" * 80)

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")

    print(
        f"[TOKENS] prompt={prompt_tokens} "
        f"completion={completion_tokens} "
        f"total={total_tokens}"
    )

    try:
        message = data["choices"][0]["message"]
        raw_content = message.get("content", "") or ""

        # Some reasoning models expose thinking separately. We ignore it.
        reasoning_content = message.get("reasoning_content")
        if reasoning_content:
            print("[STAGE 4] reasoning_content was returned separately and ignored.")

        raw_output = _normalize_model_output(raw_content, top_n)

    except Exception as e:
        print("\n" + "=" * 80)
        print("[STAGE 4 ERROR]")
        print(f"Could not parse Fireworks response: {e}")
        print(json.dumps(data, indent=2)[:4000])
        print("=" * 80)
        raise RuntimeError("Stage 4 response parsing failed.") from e

    print("\n" + "=" * 80)
    print("[NORMALIZED KIMI OUTPUT]")
    print(raw_output)
    print("=" * 80)

    print(
        f"[STAGE 4] Complete | "
        f"Latency={elapsed}ms | "
        f"Chars={len(raw_output)} | "
        f"Fallback={'yes' if used_fallback else 'no'}"
    )

    return {
        "raw_output": raw_output,
        "candidates_sent": len(candidates),
        "model": MODEL,
        "latency_ms": elapsed,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }

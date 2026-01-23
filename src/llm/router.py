from __future__ import annotations

import json
from typing import Any, Dict, List

from google.genai import types
from src.llm.gemini_client import get_client, MODEL_NAME

ROUTER_SYSTEM = """
You are a routing function for an analytics app.

Your job:
- Read the user's message and recent conversation context.
- Choose ONE tool from the allowed tool list.
- Output ONLY valid JSON matching the schema:

{
  "tool": "metrics_top_categories" | "sentiment_summary" | "rating_distribution",
  "args": { ... },
  "rationale": "short"
}

Constraints:
- If the user asks "why / reasons / issues / complaints / main issues", choose sentiment_summary.
- If the user asks for "top / best / worst / NPS / rating summary", choose metrics_top_categories.
- If the user asks for "distribution / histogram of ratings", choose rating_distribution.
- ALWAYS select a category if the tool needs it.
- The category must be chosen from the provided Allowed Categories list.
- If the user's category is not in Allowed Categories, pick the closest match from the list or fallback to metrics_top_categories.
- Output JSON only. No markdown.
"""

def route_tool(
    *,
    user_message: str,
    allowed_categories: list[str],
    recent_messages: list[dict],
) -> Dict[str, Any]:
    client = get_client()

    ctx = {
        "allowed_categories": allowed_categories[:200],  # guard
        "recent_messages": recent_messages[-6:],         # small memory
        "user_message": user_message,
    }

    prompt = json.dumps(ctx, ensure_ascii=False)

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=ROUTER_SYSTEM,
            temperature=0.0,    # stable routing
            max_output_tokens=300,
            response_mime_type="application/json",
        ),
    )

    raw = (resp.text or "").strip()
    parsed = json.loads(raw)

    # Accept dict or [dict]
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        parsed = parsed[0]

    if not isinstance(parsed, dict) or "tool" not in parsed or "args" not in parsed:
        raise ValueError(f"Bad router output: {parsed}")

    return parsed
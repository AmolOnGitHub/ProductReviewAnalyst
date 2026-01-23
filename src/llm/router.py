from __future__ import annotations

import json
from typing import Any, Dict, List

from google.genai import types
from src.llm.gemini_client import get_client, MODEL_NAME

ROUTER_SYSTEM = """
You are a tool router for a product review analytics app. Given a user message, select exactly ONE tool and return valid JSON.

## Tools

1. **general_query** — Answer general questions about the data (counts, lists, summaries, info).
   - args.query_type (string): One of:
     - "count_categories" — how many categories exist
     - "list_categories" — list all category names
     - "category_info" — get stats for a specific category (requires args.category)
     - "summary_stats" (default) — overall data summary
   - args.category (string, optional): Required only for "category_info".
   
   Use when: user asks "how many", "list all", "what categories", "tell me about", general stats, or any question that needs a text answer (not a chart).

2. **metrics_top_categories** — Show top N categories ranked by a metric (UPDATES THE CHART).
   - args.top_n (int, 1-50, default 15): Number of categories to show.
   - args.metric (string): How to rank categories. One of:
     - "review_count" (default) — most reviewed
     - "nps" — highest Net Promoter Score
     - "avg_rating" — highest average star rating
   - args.direction (string): One of:
     - "desc" (default) — highest, top, best
     - "asc" — lowest, bottom, worst
   
   Use when: user explicitly asks to "show", "display", or "update" the categories chart, or asks for rankings/comparisons.

3. **rating_distribution** — Show histogram of star ratings for ONE category (UPDATES THE CHART).
   - args.category (string, required): Must be from Allowed Categories.
   
   Use when: user asks to "show" or "display" rating distribution/histogram for a specific category.

4. **sentiment_summary** — Explain WHY customers feel a certain way about ONE category.
   - args.category (string, required): Must be from Allowed Categories.
   - args.max_reviews (int, 5-200, default 30): Reviews to analyze.
   
   Use when: user asks "why", "reasons", "complaints", "issues", "sentiments", "what do customers say" about a specific category.

5. **compare_categories** — Compare TWO categories side-by-side (UPDATES THE CHART).
   - args.category_a (string, required): Must be from Allowed Categories.
   - args.category_b (string, required): Must be from Allowed Categories.

   Use when: user asks to "compare X vs Y", "X versus Y", "which is better: X or Y", or asks differences between two categories.

## Output Format

Return ONLY this JSON (no markdown, no explanation):
{
  "tool": "<tool_name>",
  "args": { ... },
  "rationale": "<one short sentence>"
}

## Routing Rules (in priority order)

1. Questions asking "how many categories" or "total categories" → general_query with query_type="count_categories"
2. Questions asking to "list categories" or "what categories exist" → general_query with query_type="list_categories"
3. Questions asking "tell me about [category]" or info about a specific category (without asking for charts) → general_query with query_type="category_info"
4. Questions asking for overall stats or summary → general_query with query_type="summary_stats"
5. Questions asking to compare TWO categories (X vs Y / versus / which is better) → compare_categories
6. User asks "why", "reasons", "sentiments", "complaints" about a SPECIFIC CATEGORY → sentiment_summary
7. User asks to "show" or "display" rating distribution for a category → rating_distribution
8. User asks to "show top N" or "display top categories" by a metric → metrics_top_categories with direction="desc"
9. User asks to "show bottom N", "lowest", or "worst" categories by a metric → metrics_top_categories with direction="asc"
10. For compare_categories: you must output two category names that exist in Allowed Categories. If you can't find two, use general_query summary_stats.
11. If intent is truly unclear, use general_query with query_type="summary_stats".

IMPORTANT: Only use metrics_top_categories or rating_distribution when the user wants to UPDATE A CHART. For informational questions, use general_query or sentiment_summary.
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

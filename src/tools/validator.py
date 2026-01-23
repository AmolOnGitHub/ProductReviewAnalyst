from __future__ import annotations
from typing import Any, Dict


ALLOWED_TOOLS = {"metrics_top_categories", "sentiment_summary", "rating_distribution"}


def validate_tool_call(tc: Dict[str, Any], allowed_categories: set[str]) -> Dict[str, Any]:
    tool = tc.get("tool")
    args = tc.get("args", {})

    if tool not in ALLOWED_TOOLS or not isinstance(args, dict):
        return {"tool": "metrics_top_categories", "args": {"top_n": 10}, "rationale": "fallback_invalid_tool"}

    if tool == "metrics_top_categories":
        top_n = args.get("top_n", 10)
        if not isinstance(top_n, int) or top_n < 1 or top_n > 50:
            top_n = 10
        return {"tool": tool, "args": {"top_n": top_n}, "rationale": tc.get("rationale", "")}

    if tool in {"sentiment_summary", "rating_distribution"}:
        cat = args.get("category")
        if not isinstance(cat, str) or not cat.strip():
            # no category supplied -> fallback
            return {"tool": "metrics_top_categories", "args": {"top_n": 10}, "rationale": "fallback_missing_category"}

        cat = cat.strip()

        # Enforce category access strictly
        if cat not in allowed_categories:
            return {"tool": "metrics_top_categories", "args": {"top_n": 10}, "rationale": "fallback_category_not_allowed"}

        if tool == "sentiment_summary":
            max_reviews = args.get("max_reviews", 30)
            if not isinstance(max_reviews, int) or max_reviews < 5 or max_reviews > 200:
                max_reviews = 30
            return {"tool": tool, "args": {"category": cat, "max_reviews": max_reviews}, "rationale": tc.get("rationale", "")}

        return {"tool": tool, "args": {"category": cat}, "rationale": tc.get("rationale", "")}

    return {"tool": "metrics_top_categories", "args": {"top_n": 10}, "rationale": "fallback_default"}
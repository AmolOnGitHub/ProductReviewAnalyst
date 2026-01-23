from __future__ import annotations
from typing import Any, Dict


ALLOWED_TOOLS = {
    "metrics_top_categories",
    "sentiment_summary",
    "rating_distribution",
    "general_query",
    "compare_categories",
}


def validate_tool_call(tc: Dict[str, Any], allowed_categories: set[str]) -> Dict[str, Any]:
    tool = tc.get("tool")
    args = tc.get("args", {})

    # Invalid tool / schema
    if tool not in ALLOWED_TOOLS or not isinstance(args, dict):
        return {
            "tool": "general_query",
            "args": {"query_type": "summary_stats"},
            "rationale": "fallback_invalid_tool",
            "fallback_reason": "I couldn't determine a valid action for that request.",
        }

    # General queries
    if tool == "general_query":
        query_type = args.get("query_type", "summary_stats")
        if query_type not in {
            "count_categories",
            "list_categories",
            "category_info",
            "summary_stats",
        }:
            query_type = "summary_stats"

        result = {
            "tool": tool,
            "args": {"query_type": query_type},
            "rationale": tc.get("rationale", ""),
        }

        if query_type == "category_info":
            cat = args.get("category")
            if isinstance(cat, str) and cat.strip() and cat.strip() in allowed_categories:
                result["args"]["category"] = cat.strip()
            else:
                result["args"]["query_type"] = "summary_stats"
                result["fallback_reason"] = (
                    "That category isn't available based on your access, "
                    "so I'm showing overall summary statistics instead."
                )

        return result

    # Top categories
    if tool == "metrics_top_categories":
        top_n = args.get("top_n", 15)
        if not isinstance(top_n, int) or top_n < 1 or top_n > 52:
            top_n = 15

        metric = args.get("metric", "review_count")
        if metric not in {"review_count", "nps", "avg_rating"}:
            metric = "review_count"

        return {
            "tool": tool,
            "args": {"top_n": top_n, "metric": metric},
            "rationale": tc.get("rationale", ""),
        }

    # Compare categories
    if tool == "compare_categories":
        a = args.get("category_a")
        b = args.get("category_b")

        if not isinstance(a, str) or not a.strip() or not isinstance(b, str) or not b.strip():
            return {
                "tool": "metrics_top_categories",
                "args": {"top_n": 15, "metric": "review_count"},
                "rationale": "fallback_missing_compare_categories",
                "fallback_reason": "I couldn't identify two valid categories to compare.",
            }

        a = a.strip()
        b = b.strip()

        if a == b:
            return {
                "tool": "rating_distribution",
                "args": {"category": a},
                "rationale": "fallback_same_category_compare",
                "fallback_reason": "You asked to compare the same category with itself, so I showed its rating distribution instead.",
            }

        if a not in allowed_categories or b not in allowed_categories:
            return {
                "tool": "metrics_top_categories",
                "args": {"top_n": 15, "metric": "review_count"},
                "rationale": "fallback_compare_category_not_allowed",
                "fallback_reason": "One or both of the categories you asked to compare aren't available based on your access.",
            }

        return {
            "tool": tool,
            "args": {"category_a": a, "category_b": b},
            "rationale": tc.get("rationale", ""),
        }

    # Sentiment / distribution
    if tool in {"sentiment_summary", "rating_distribution"}:
        cat = args.get("category")

        if not isinstance(cat, str) or not cat.strip():
            return {
                "tool": "metrics_top_categories",
                "args": {"top_n": 15},
                "rationale": "fallback_missing_category",
                "fallback_reason": "I couldn't identify which category you meant.",
            }

        cat = cat.strip()

        if cat not in allowed_categories:
            return {
                "tool": "metrics_top_categories",
                "args": {"top_n": 15},
                "rationale": "fallback_category_not_allowed",
                "fallback_reason": "That category isn't available based on your access.",
            }

        if tool == "sentiment_summary":
            max_reviews = args.get("max_reviews", 30)
            if not isinstance(max_reviews, int) or max_reviews < 5 or max_reviews > 200:
                max_reviews = 30

            return {
                "tool": tool,
                "args": {"category": cat, "max_reviews": max_reviews},
                "rationale": tc.get("rationale", ""),
            }

        return {
            "tool": tool,
            "args": {"category": cat},
            "rationale": tc.get("rationale", ""),
        }

    # Final safety fallback
    return {
        "tool": "metrics_top_categories",
        "args": {"top_n": 15, "metric": "review_count"},
        "rationale": "fallback_default",
        "fallback_reason": "I couldn't safely complete that request, so I showed a general overview instead.",
    }
from __future__ import annotations
from typing import Any, Dict

import pandas as pd
from sqlalchemy.orm import Session

from src.metrics import category_metrics
from src.sentiment_cache_service import analyze_reviews_with_cache


def run_tool(
    *,
    db: Session,
    visible_df: pd.DataFrame,
    tool: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    mdf = category_metrics(visible_df)
    
    if tool == "general_query":
        query_type = args.get("query_type", "summary_stats")
        cat = args.get("category")
        
        if query_type == "count_categories":
            return {"total_categories": int(mdf["category"].nunique()), "total_reviews": int(visible_df.shape[0])}
        
        if query_type == "list_categories":
            categories = sorted(mdf["category"].unique().tolist())
            return {"categories": categories, "count": len(categories)}
        
        if query_type == "category_info" and cat:
            row = mdf[mdf["category"] == cat]
            if row.empty:
                return {"error": f"Category '{cat}' not found"}
            info = row.iloc[0].to_dict()
            return {"category": cat, "info": info}
        
        # summary_stats (default)
        return {
            "total_categories": int(mdf["category"].nunique()),
            "total_reviews": int(visible_df.shape[0]),
            "avg_rating_overall": float(visible_df["rating"].mean()) if "rating" in visible_df else None,
            "top_category_by_reviews": mdf.sort_values("review_count", ascending=False).iloc[0]["category"] if not mdf.empty else None,
        }

    if tool == "metrics_top_categories":
        top_n = args["top_n"]
        metric = args.get("metric", "review_count")
        mdf_sorted = mdf.sort_values(metric, ascending=False).head(top_n)
        return {"metrics": mdf_sorted.to_dict(orient="records"), "sorted_by": metric}

    if tool == "rating_distribution":
        cat = args["category"]
        sub = visible_df[visible_df["category"] == cat].dropna(subset=["rating"])
        dist = sub["rating"].value_counts().sort_index().to_dict()
        return {"category": cat, "rating_distribution": dist}

    if tool == "sentiment_summary":
        cat = args["category"]
        max_reviews = args["max_reviews"]
        reviews = (
            visible_df[(visible_df["category"] == cat) & (visible_df["review_text"].notna())]["review_text"]
            .astype(str)
            .tolist()
        )
        out = analyze_reviews_with_cache(db, reviews, max_reviews=max_reviews, batch_size=10, timeout_s=15.0)
        return {"category": cat, "sentiment": out}

    if tool == "compare_categories":
        a = args["category_a"]
        b = args["category_b"]

        row_a = mdf[mdf["category"] == a]
        row_b = mdf[mdf["category"] == b]

        if row_a.empty or row_b.empty:
            return {"error": "one_or_both_categories_not_found", "category_a": a, "category_b": b}

        return {
            "category_a": a,
            "category_b": b,
            "metrics_a": row_a.iloc[0].to_dict(),
            "metrics_b": row_b.iloc[0].to_dict(),
        }
    
    return {"error": "unknown_tool"}
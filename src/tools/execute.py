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
    if tool == "metrics_top_categories":
        top_n = args["top_n"]
        mdf = category_metrics(visible_df).head(top_n)
        return {"metrics": mdf.to_dict(orient="records")}

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

    return {"error": "unknown_tool"}
from __future__ import annotations
import pandas as pd


def compute_nps(ratings: pd.Series) -> float:
    """
    NPS = (%promoters - %detractors) * 100
    promoters: 4-5
    passives: 3
    detractors: 1-2
    """
    r = pd.to_numeric(ratings, errors="coerce").dropna()
    if len(r) == 0:
        return float("nan")

    promoters = (r >= 4).sum()
    detractors = (r <= 2).sum()
    total = len(r)

    return ((promoters / total) - (detractors / total)) * 100.0


def category_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expects columns: category, rating
    Returns per-category: review_count, avg_rating, nps
    """
    if df.empty:
        return pd.DataFrame(columns=["category", "review_count", "avg_rating", "nps"])

    g = df.groupby("category", dropna=False)

    out = g["rating"].agg(
        review_count="count",
        avg_rating="mean",
    ).reset_index()

    # NPS per category
    out["nps"] = g["rating"].apply(compute_nps).values

    # nice formatting sorts
    out = out.sort_values(["review_count", "avg_rating"], ascending=[False, False]).reset_index(drop=True)
    return out
from __future__ import annotations
import pandas as pd

from src.data_cleaning import (
    normalize_rating,
    normalize_date,
    extract_categories,
)


def build_analytics_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a cleaned dataframe with:
    - one row per (review x category)
    """

    df = raw_df.copy()

    df["rating"] = normalize_rating(df["reviews.rating"])
    df["review_date"] = normalize_date(df["reviews.date"])
    df["categories_list"] = extract_categories(df["categories"])

    # Drop rows without essential fields
    df = df.dropna(subset=["rating", "review_date"])

    # Explode categories
    df = df.explode("categories_list")

    df = df.rename(columns={
        "id": "product_id",
        "name": "product_name",
        "categories_list": "category",
        "reviews.text": "review_text",
        "reviews.title": "review_title",
    })

    # Keep only neccessary columns
    return df[
        [
            "product_id",
            "product_name",
            "category",
            "rating",
            "review_date",
            "review_text",
            "review_title",
        ]
    ]
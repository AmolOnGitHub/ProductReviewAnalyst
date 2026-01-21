from __future__ import annotations
import pandas as pd
import re


BLOCKLIST = {
    "buy a kindle",
    "amazon.co.uk",
    "mazon.co.uk",
}

def is_valid_category(cat: str) -> bool:
    if not cat:
        return False

    c = cat.strip().lower()

    if c in BLOCKLIST:
        return False

    if len(c) < 3:
        return False

    # must contain at least one alphabet
    if not re.search(r"[a-z]", c):
        return False

    # reject URLs / domains
    if "." in c and " " not in c:
        return False

    return True


def normalize_rating(series: pd.Series) -> pd.Series:
    """
    Ensure ratings are numeric and in [1,5].
    """
    s = pd.to_numeric(series, errors="coerce")
    return s[(s >= 1) & (s <= 5)]


def normalize_date(series: pd.Series) -> pd.Series:
    """
    Parse review dates.
    """
    return pd.to_datetime(series, errors="coerce", utc=True)


def extract_categories(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .apply(
            lambda x: [
                c.strip()
                for c in x.split(",")
                if is_valid_category(c)
            ]
        )
    )
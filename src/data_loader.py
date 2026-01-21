from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

EXPECTED_COLUMNS = [
    "id","asins","brand","categories","colors","dateAdded","dateUpdated","dimension","ean","keys",
    "manufacturer","manufacturerNumber","name","prices","reviews.date","reviews.doRecommend",
    "reviews.numHelpful","reviews.rating","reviews.sourceURLs","reviews.text","reviews.title",
    "reviews.userCity","reviews.userProvince","reviews.username","sizes","upc","weight",
]


@dataclass(frozen=True)
class LoadResult:
    df: pd.DataFrame
    missing_cols: list[str]
    extra_cols: list[str]


def load_reviews_csv(csv_path: str | Path) -> LoadResult:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found at: {csv_path.resolve()}")

    df = pd.read_csv(csv_path)

    cols = list(df.columns)
    missing = [c for c in EXPECTED_COLUMNS if c not in cols]
    extra = [c for c in cols if c not in EXPECTED_COLUMNS]

    return LoadResult(df=df, missing_cols=missing, extra_cols=extra)
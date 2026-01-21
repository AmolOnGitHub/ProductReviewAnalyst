from sqlalchemy.orm import Session
import pandas as pd

from src.access_control import get_allowed_categories
from src.analytics_df import build_analytics_df
from src.data_loader import load_reviews_csv


def load_analytics_df_for_user(
    *,
    db: Session,
    user_id: int,
    user_role: str,
    csv_path: str,
) -> pd.DataFrame:
    """
    Returns an analytics dataframe filtered by category access.
    Admins see everything.
    Analysts see only allowed categories.
    """

    raw = load_reviews_csv(csv_path).df
    df = build_analytics_df(raw)

    if user_role == "admin":
        return df

    allowed_categories = get_allowed_categories(db, user_id)

    # IMPORTANT: enforce access
    df = df[df["category"].isin(allowed_categories)]

    return df
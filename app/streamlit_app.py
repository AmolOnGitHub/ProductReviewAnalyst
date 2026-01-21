import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
                    
from src.data_loader import load_reviews_csv

st.set_page_config(page_title="Review Analytics MVP", layout="wide")

st.title("Review Analytics MVP — Dataset Check")

csv_path = st.text_input("CSV path", value="./data/amazon_products.csv")

if st.button("Load dataset"):
    try:
        result = load_reviews_csv(csv_path)
        df = result.df

        if result.missing_cols:
            st.error(f"Missing columns ({len(result.missing_cols)}): {result.missing_cols}")
        if result.extra_cols:
            st.warning(f"Extra columns ({len(result.extra_cols)}): {result.extra_cols}")

        st.success(f"Loaded {len(df):,} rows × {len(df.columns)} columns")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Rows", f"{len(df):,}")
        with c2:
            st.metric("Non-null reviews.text", f"{df['reviews.text'].notna().sum():,}")
        with c3:
            st.metric("Non-null reviews.rating", f"{df['reviews.rating'].notna().sum():,}")

        st.subheader("Preview (first 50 rows)")
        st.dataframe(df.head(50), use_container_width=True)

        st.subheader("Ratings distribution (raw)")
        if "reviews.rating" in df.columns:
            st.write(df["reviews.rating"].value_counts(dropna=False).sort_index())

    except Exception as e:
        st.exception(e)
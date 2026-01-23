import sys
from pathlib import Path
import streamlit as st
import pandas as pd
from sqlalchemy import text

# Add root to sys.path to allow src imports
ROOT = Path(__file__).resolve().parents[2]  # app/pages/admin.py -> app/pages -> app -> ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import init_db, SessionLocal, db_healthcheck
from src.data_loader import load_reviews_csv
from src.analytics_df import build_analytics_df
from src.category_service import upsert_categories
from src.models import Category, User, UserCategoryAccess
from src.access_control import set_user_categories
from src.user_service import create_user
from src.trace_service import fetch_recent_traces


st.set_page_config(page_title="Admin Tools", layout="wide")

if "user" not in st.session_state or st.session_state.user is None:
    st.warning("Please login first.")
    st.stop()

if st.session_state.user["role"] != "admin":
    st.error("Access denied. Admin role required.")
    st.stop()

st.title("Admin Tools")

csv_path = st.text_input("CSV path", value="./data/amazon_products.csv")

with st.expander("Developer tools", expanded=True):
    # DB Healthcheck
    st.subheader("Database health")
    if db_healthcheck():
        st.success("PostgreSQL connection OK")
    else:
        st.error("Database connection failed")

    # DB Initialization
    st.subheader("Database setup")
    if st.button("Initialize DB tables"):
        init_db()
        st.success("Tables created / verified")

    if st.button("Show table counts"):
        with SessionLocal() as s:
            counts = {}
            for t in [
                "users",
                "categories",
                "user_category_access",
                "conversations",
                "message_traces",
            ]:
                counts[t] = s.execute(
                    text(f"SELECT COUNT(*) FROM {t}")
                ).scalar()
        st.write(counts)

    # Category Ingestion
    if st.button("Ingest categories into DB"):
        with SessionLocal() as db:
            result = load_reviews_csv(csv_path)
            analytics_df = build_analytics_df(result.df)

            categories = set(analytics_df["category"].dropna().unique())
            created = upsert_categories(db, categories)

            st.success(f"Categories ingested. New categories added: {created}")
            st.write(f"Total unique categories: {len(categories)}")

    with st.expander("View categories"):
        with SessionLocal() as db:
            categories = (
                db.query(Category)
                .order_by(Category.name.asc())
                .all()
            )
        st.write(f"Total categories: {len(categories)}")
        st.dataframe(
            [{"id": c.id, "name": c.name} for c in categories],
            width=800,
        )


with st.expander("LLM Trace Viewer", expanded=False):
    st.subheader("LLM Trace Viewer")

    trace_limit = st.slider("Number of traces", 10, 200, 50)

    with SessionLocal() as db:
        traces = fetch_recent_traces(db, limit=trace_limit)

    if not traces:
        st.info("No traces found.")
    else:
        trace_rows = []
        for t in traces:
            prompt_payload = t.prompt_payload if isinstance(t.prompt_payload, dict) else {}
            retrieval_payload = t.retrieval_payload if isinstance(t.retrieval_payload, dict) else {}
            tool_payload = retrieval_payload.get("tool")
            if not isinstance(tool_payload, dict):
                tool_payload = {}
            router_payload = prompt_payload.get("router")
            if not isinstance(router_payload, dict):
                router_payload = {}

            user_query = t.user_query or ""
            short_query = user_query
            if len(user_query) > 80:
                short_query = f"{user_query[:80]}..."

            tool_name = tool_payload.get("tool") or router_payload.get("tool") or ""
            fallback_reason = tool_payload.get("fallback_reason") or ""

            trace_rows.append(
                {
                    "time": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "user_id": t.user_id,
                    "tool": tool_name,
                    "fallback_reason": fallback_reason,
                    "query": short_query,
                }
            )

        st.dataframe(trace_rows, width='stretch')

        selected_idx = st.selectbox(
            "Inspect trace",
            options=list(range(len(traces))),
            format_func=lambda i: f"{trace_rows[i]['time']} - {trace_rows[i]['tool']}",
        )

        t = traces[selected_idx]
        prompt_payload = t.prompt_payload if isinstance(t.prompt_payload, dict) else {}
        retrieval_payload = t.retrieval_payload if isinstance(t.retrieval_payload, dict) else {}
        response_payload = t.response_payload if isinstance(t.response_payload, dict) else {}
        router_payload = prompt_payload.get("router")
        if not isinstance(router_payload, dict):
            router_payload = {}
        tool_payload = retrieval_payload.get("tool")
        if not isinstance(tool_payload, dict):
            tool_payload = {}
        tool_result = retrieval_payload.get("tool_result")

        st.markdown("### Full Trace")

        st.markdown("#### User query")
        st.json({"user_query": t.user_query})

        st.markdown("#### Router decision")
        st.json(router_payload)

        st.markdown("#### Validator enforcement")
        st.json(tool_payload)

        st.markdown("#### Tool execution")
        st.json(tool_result)

        st.markdown("#### Final response")
        st.json(response_payload)


# Create Analyst User
st.subheader("Create analyst")

with SessionLocal() as db:
    categories = db.query(Category).order_by(Category.name).all()

with st.form("create_analyst_form"):
    analyst_email = st.text_input("Analyst email")
    analyst_password = st.text_input("Analyst temporary password", type="password")

    assign_now = st.checkbox("Assign categories now", value=True)

    selected_category_ids = []
    if assign_now:
        selected_category_ids = st.multiselect(
            "Allowed categories",
            options=[c.id for c in categories],
            format_func=lambda cid: next(c.name for c in categories if c.id == cid),
        )

    submitted = st.form_submit_button("Create analyst")

    if submitted:
        if not analyst_email or not analyst_password:
            st.error("Email and password required.")
        else:
            try:
                with SessionLocal() as db:
                    # Note: create_user function needs to be imported
                    user = create_user(db, analyst_email, analyst_password, role="analyst")
                    if assign_now and selected_category_ids:
                        set_user_categories(db, user.id, selected_category_ids)

                st.success("Analyst created.")
                st.info("Share the temporary password with the analyst.")
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.exception(e)


# Analyst Category Access Management
st.subheader("Analyst category access")

with SessionLocal() as db:
    analysts = (
        db.query(User)
        .filter(User.role == "analyst", User.is_active.is_(True))
        .all()
    )
    categories = db.query(Category).order_by(Category.name).all()

if not analysts:
    st.info("No analysts found.")
else:
    analyst_email = st.selectbox(
        "Select analyst",
        options=[a.email for a in analysts],
    )

    selected_analyst = next(
        a for a in analysts if a.email == analyst_email # type: ignore
    )

    with SessionLocal() as db:
        current_ids = {
            r.category_id
            for r in db.query(UserCategoryAccess)
            .filter(UserCategoryAccess.user_id == selected_analyst.id)
            .all()
        }

    selected_category_ids = st.multiselect(
        "Allowed categories",
        options=[c.id for c in categories],
        default=list(current_ids),
        format_func=lambda cid: next(
            c.name for c in categories if c.id == cid
        ),
        key="access_multiselect"
    )

    if st.button("Save category access"):
        with SessionLocal() as db:
            set_user_categories(
                db,
                selected_analyst.id,
                selected_category_ids,
            )
        st.success("Category access updated")

    st.subheader("Users (access versions)")

    with SessionLocal() as db:
        users = db.query(User).order_by(User.role.asc(), User.email.asc()).all()

    st.dataframe(
        [{"email": u.email, "role": u.role, "is_active": u.is_active, "access_version": u.access_version} for u in users],
        width=800,  
    )


## Dataset Preview
st.subheader("Dataset Preview")
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
        st.dataframe(df.head(50), width=800)

        st.subheader("Ratings distribution (raw)")
        if "reviews.rating" in df.columns:
            st.write(df["reviews.rating"].value_counts(dropna=False).sort_index())

    except Exception as e:
        st.exception(e)

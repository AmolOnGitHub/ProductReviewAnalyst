import sys
from pathlib import Path
from dotenv import load_dotenv

# Path + .env setup
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


import pandas as pd
import streamlit as st
from sqlalchemy import text
from typing import Tuple
import plotly.express as px

from src.data_loader import load_reviews_csv
from src.user_service import authenticate_user, create_user
from src.db import init_db, SessionLocal, db_healthcheck
from src.analytics_df import build_analytics_df
from src.category_service import upsert_categories
from src.models import Category, User, UserCategoryAccess
from src.access_control import set_user_categories, get_allowed_categories
from src.analytics_access import load_analytics_df_for_user
from src.metrics import category_metrics
from src.plots import plot_nps_by_category, plot_rating_distribution, plot_avg_rating_by_category
from src.sentiment_cache_service import analyze_reviews_with_cache
from src.trace_service import get_or_create_conversation, log_trace

from src.llm.router import route_tool
from src.llm.response_writer import write_response

from src.tools.validator import validate_tool_call
from src.tools.execute import run_tool

## Streamlit Config
st.set_page_config(page_title="Review Analytics MVP", layout="wide")


## Cached Helpers
@st.cache_data(show_spinner=False)
def _load_raw_df(csv_path: str) -> pd.DataFrame:
    return load_reviews_csv(csv_path).df


@st.cache_data(show_spinner=False)
def _build_analytics_df(csv_path: str) -> pd.DataFrame:
    raw = _load_raw_df(csv_path)
    return build_analytics_df(raw)


@st.cache_data(show_spinner=False)
def _filter_df_by_categories(
    analytics_df: pd.DataFrame,
    allowed_categories: Tuple[str, ...],
    access_version: int,
) -> pd.DataFrame:
    # access_version intentionally unused; it busts cache when access changes
    return analytics_df[analytics_df["category"].isin(allowed_categories)]


@st.cache_data(show_spinner=False)
def _compute_category_metrics(filtered_df: pd.DataFrame) -> pd.DataFrame:
    return category_metrics(filtered_df)


## Session State 
if "user" not in st.session_state:
    st.session_state.user = None

if "plot_state" not in st.session_state:
    st.session_state.plot_state = {
        "top_n": 15,
        "rating_dist_category": None,
    }


## Login Gate
if st.session_state.user is None:
    st.title("Login")

    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            with SessionLocal() as db:
                user = authenticate_user(db, email, password)
                if user:
                    st.session_state.user = {
                        "id": user.id,
                        "email": user.email,
                        "role": user.role,
                    }
                    st.success("Logged in")
                    st.rerun()
                else:
                    st.error("Invalid credentials")

    st.stop()
    

## Sidebar
st.sidebar.write(f"Logged in as: {st.session_state.user['email']}")
st.sidebar.write(f"Role: {st.session_state.user['role']}")
if st.session_state.user["role"] != "admin":
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == st.session_state.user["id"]).first()
        st.sidebar.write(f"Access version: {user.access_version if user else 0}")



if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()


## Main Page
st.title("Review Analytics MVP — Dataset Check")
csv_path = st.text_input("CSV path", value="./data/amazon_products.csv")


## Admin only tools
if st.session_state.user["role"] == "admin":
    with st.expander("Developer tools"):

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
                width='stretch',
            )


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
                            user = create_user(db, analyst_email, analyst_password, role="analyst")
                            if assign_now and selected_category_ids:
                                set_user_categories(db, user.id, selected_category_ids)

                        st.success("Analyst created.")
                        st.info("Share the temporary password with the analyst and rotate it later (we'll add change-password).")
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
                width='stretch',  # if you haven’t switched yet
            )


## Dataset Preview
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
        st.dataframe(df.head(50), width='stretch')

        st.subheader("Ratings distribution (raw)")
        if "reviews.rating" in df.columns:
            st.write(df["reviews.rating"].value_counts(dropna=False).sort_index())

    except Exception as e:
        st.exception(e)


## Category Metrics
st.subheader("Category metrics (ratings + NPS)")

if st.button("Compute metrics"):
    with SessionLocal() as db:
        df = load_analytics_df_for_user(
            db=db,
            user_id=st.session_state.user["id"],
            user_role=st.session_state.user["role"],
            csv_path=csv_path,
        )

    mdf = category_metrics(df)

    st.write(f"Categories visible to you: {mdf['category'].nunique()}")
    st.dataframe(mdf, width='stretch')

    # Optional: quick global metrics over visible data
    if not df.empty:
        st.markdown("**Overall (visible data):**")
        overall_nps = ((df["rating"] >= 4).sum() / len(df) - (df["rating"] <= 2).sum() / len(df)) * 100
        st.write({
            "reviews": int(len(df)),
            "avg_rating": float(df["rating"].mean()),
            "nps": float(overall_nps),
        })


## Visualizations
st.subheader("Visualizations")

# Controls live OUTSIDE any button so they persist across reruns
top_n = st.slider("Top N categories (by review count)", 5, 52, 15)

with SessionLocal() as db:
    role = st.session_state.user["role"]
    user_id = st.session_state.user["id"]

    analytics_df = _build_analytics_df(csv_path)

    if role == "admin":
        visible_df = analytics_df
    else:
        allowed = get_allowed_categories(db, user_id)

        # fetch access_version (cache-buster for access changes)
        user = db.query(User).filter(User.id == user_id).first()
        access_version = int(user.access_version) if user else 0

        visible_df = _filter_df_by_categories(
            analytics_df,
            tuple(sorted(allowed)),
            access_version,
        )

mdf = _compute_category_metrics(visible_df)

if mdf.empty:
    st.info("No data available for your current access.")
    st.stop()

mdf_top = mdf.sort_values("review_count", ascending=False).head(top_n)

# NPS by category
fig_nps = px.bar(mdf_top, x="category", y="nps", title="NPS by Category")
fig_nps.update_layout(xaxis_title="Category", yaxis_title="NPS", xaxis_tickangle=-45)
st.plotly_chart(fig_nps, width='stretch')

# Avg rating by category
fig_avg = px.bar(mdf_top, x="category", y="avg_rating", title="Average Rating by Category")
fig_avg.update_layout(xaxis_title="Category", yaxis_title="Average Rating", xaxis_tickangle=-45)
st.plotly_chart(fig_avg, width='stretch')

# Rating distribution for selected category
category_options = sorted(mdf["category"].dropna().unique())
selected_cat = st.selectbox("Select category for rating distribution", category_options)

sub = visible_df[visible_df["category"] == selected_cat].dropna(subset=["rating"])
fig_hist = px.histogram(sub, x="rating", nbins=5, title=f"Rating Distribution — {selected_cat}")
fig_hist.update_layout(xaxis_title="Rating", yaxis_title="Count")
st.plotly_chart(fig_hist, width='stretch')


## Sentiment Analysis
st.subheader("Why customers feel this way")

selected_category_for_sentiment = st.selectbox(
    "Select category for sentiment analysis",
    sorted(mdf["category"].unique()),
    key="sentiment_category",
)

max_reviews = st.slider(
    "Max reviews to analyze (cost control)",
    10, 200, 50,
)

if st.button("Analyze sentiment"):
    reviews = (
        visible_df[
            (visible_df["category"] == selected_category_for_sentiment)
            & (visible_df["review_text"].notna())
        ]["review_text"]
        .tolist()
    )

    with st.spinner("Analyzing reviews with Gemini..."):
        with SessionLocal() as db:
            sentiment_out = analyze_reviews_with_cache(
                db,
                reviews,
                max_reviews=max_reviews,
                batch_size=10,
                timeout_s=15.0,
            )

        st.write(sentiment_out)
        st.dataframe(
            [{"reason": r, "count": c} for r, c in sentiment_out["top_reasons"]],
            width='stretch',
        )


## Chat
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []  # list[{"role": "user"|"assistant", "content": str}]
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []  # list[{"role": "user"|"assistant", "content": str}]
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

st.subheader("Chat")

# Render chat history
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Allowed categories for routing (access-filtered)
allowed_categories = sorted(mdf["category"].dropna().unique().tolist())

if not allowed_categories:
    st.info("No categories available for chat based on your access. Ask an admin to assign categories.")
    st.stop()

user_text = st.chat_input("Ask about ratings, NPS, sentiment reasons, or distributions...")

if user_text:
    # show user msg
    st.session_state.chat_messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.write(user_text)

    assistant_text = "Sorry — I couldn't process that."
    router_out = None
    validated = None
    tool_result = None

    with SessionLocal() as db:
        # ensure conversation exists
        if st.session_state.conversation_id is None:
            conv = get_or_create_conversation(
                db,
                user_id=st.session_state.user["id"],
                title="Streamlit chat",
            )
            st.session_state.conversation_id = conv.id

        conversation_id = st.session_state.conversation_id
        user_id = st.session_state.user["id"]

        # Build small “memory” from recent chat messages
        recent_msgs = st.session_state.chat_messages[-6:]
        # Convert to a compact structure for the router
        recent_for_router = [{"role": m["role"], "content": m["content"]} for m in recent_msgs]

        # Route tool via Gemini
        try:
            router_out = route_tool(
                user_message=user_text,
                allowed_categories=allowed_categories,
                recent_messages=recent_for_router,
            )
        except Exception as e:
            router_out = {"tool": "metrics_top_categories", "args": {"top_n": 10}, "rationale": f"router_error: {e}"}

        print("Router output:", router_out)
        # Validate tool call (strict access enforcement)
        validated = validate_tool_call(router_out, allowed_categories=set(allowed_categories))

        # Execute tool on access-filtered data
        tool_result = run_tool(
            db=db,
            visible_df=visible_df,
            tool=validated["tool"],
            args=validated["args"],
        )

        # Generate assistant response
        assistant_text = write_response(
            user_message=user_text,
            tool_name=validated["tool"],
            tool_args=validated["args"],
            tool_result=tool_result,
            recent_messages=recent_for_router,
        )

        # Log trace for debugging/traceability
        log_trace(
            db,
            conversation_id=conversation_id,
            user_id=user_id,
            user_query=user_text,
            prompt_payload={
                "router": {
                    "allowed_categories_count": len(allowed_categories),
                    "recent_messages": recent_for_router,
                },
                "router_output": router_out,
            },
            retrieval_payload={
                "validated_tool_call": validated,
                "tool_result": tool_result,
            },
            response_payload={
                "assistant_text": assistant_text,
                "tool_used": validated["tool"],
            },
            plot_payload=None,
        )

    # Show assistant
    st.session_state.chat_messages.append({"role": "assistant", "content": assistant_text})
    with st.chat_message("assistant"):
        st.write(assistant_text)
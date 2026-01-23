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
from src.sentiment_cache_service import analyze_reviews_with_cache
from src.trace_service import get_or_create_conversation, log_trace

from src.llm.router import route_tool
from src.llm.response_writer import write_response

from src.tools.validator import validate_tool_call
from src.tools.execute import run_tool


def apply_state_aware_response(
    *,
    tool: str,
    args: dict,
    prev_state: dict,
    assistant_text: str,
) -> str:
    """
    Rewrites assistant responses to acknowledge existing UI state.
    Does NOT change tool execution or plots.
    """

    # Already comparing the same pair
    if tool == "compare_categories":
        a, b = args["category_a"], args["category_b"]
        if prev_state.get("compare_pair") == (a, b):
            return f"Still comparing **{a}** vs **{b}** — no changes needed. Check the chart on the left."
        return assistant_text

    # Top categories state awareness
    if tool == "metrics_top_categories":
        prev_metric = prev_state.get("top_metric")
        prev_top_n = prev_state.get("top_n")

        new_metric = args.get("metric", prev_metric)
        new_top_n = args.get("top_n", prev_top_n)

        changes = []
        if new_metric != prev_metric:
            changes.append(f"ranking by **{new_metric.replace('_', ' ')}**")
        if new_top_n != prev_top_n:
            changes.append(f"showing top **{new_top_n}**")

        if changes:
            return f"Updated view — now {' and '.join(changes)}. Check the chart on the left."
        else:
            return "This view is already up to date. Check the chart on the left."

    # Rating distribution already visible
    if tool == "rating_distribution":
        cat = args["category"]
        if prev_state.get("rating_dist_category") == cat:
            return f"Already showing the rating distribution for **{cat}**."
        return assistant_text

    return assistant_text


## Streamlit Config
st.set_page_config(page_title="Analytics & Chat", layout="wide")


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

if "top_n" not in st.session_state:
    st.session_state.top_n = 15

if "top_metric" not in st.session_state:
    st.session_state.top_metric = "review_count"

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

if "compare_pair" not in st.session_state:
    st.session_state.compare_pair = None


## Login Gate
if st.session_state.user is None:
    # Hide sidebar nav on login screen
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )
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


# Hide sidebar page navigation for non-admins so they can't access Admin Tools
if st.session_state.user["role"] != "admin":
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )

if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()


## Main Page
# st.title("Review Analytics MVP")
csv_path = "./data/amazon_products.csv"
# csv_path = st.sidebar.text_input("CSV path", value="./data/amazon_products.csv")


# Role, ID and permissions mapping
with SessionLocal() as db:
    role = st.session_state.user["role"]
    user_id = st.session_state.user["id"]
    analytics_df = _build_analytics_df(csv_path)

    if role == "admin":
        visible_df = analytics_df
    else:
        allowed = get_allowed_categories(db, user_id)
        # fetch access_version
        user = db.query(User).filter(User.id == user_id).first()
        access_version = int(user.access_version) if user else 0

        visible_df = _filter_df_by_categories(
            analytics_df,
            tuple(sorted(allowed)),
            access_version,
        )

mdf = _compute_category_metrics(visible_df)

# Filter: Remove categories with < 10 reviews
mdf = mdf[mdf["review_count"] >= 10]
visible_df = visible_df[visible_df["category"].isin(mdf["category"])]

if mdf.empty:
    st.info("No data available for your current access.")
    st.stop()

allowed_categories = sorted(mdf["category"].dropna().unique().tolist())
if not allowed_categories:
    st.info("No categories available for you. Ask an admin to assign category access.")
    st.stop()


left, right = st.columns([1, 1], gap="large")

# Left: Analytics & Plots
with left:
    st.header("Analytics")

    # Top-N slice by selected metric (controlled via chat)
    top_n = int(st.session_state.top_n)
    top_metric = st.session_state.top_metric
    metric_labels = {"review_count": "Review Count", "nps": "NPS", "avg_rating": "Average Rating"}
    metric_label = metric_labels.get(top_metric, "Review Count")
    
    mdf_top = mdf.sort_values(top_metric, ascending=False).head(top_n)

    # If compare is active, show compare chart; else show top chart
    if st.session_state.compare_pair is not None:
        a, b = st.session_state.compare_pair

        # Get metrics rows from mdf (already filtered to >=10 reviews)
        ra = mdf[mdf["category"] == a]
        rb = mdf[mdf["category"] == b]

        if ra.empty or rb.empty:
            st.session_state.compare_pair = None  # invalid now; fallback to top chart
        else:
            ra = ra.iloc[0]
            rb = rb.iloc[0]

            cmp_df = pd.DataFrame([
                {"category": a, "metric": "Review Count", "value": float(ra["review_count"])},
                {"category": b, "metric": "Review Count", "value": float(rb["review_count"])},
                {"category": a, "metric": "Avg Rating", "value": float(ra["avg_rating"])},
                {"category": b, "metric": "Avg Rating", "value": float(rb["avg_rating"])},
                {"category": a, "metric": "NPS", "value": float(ra["nps"])},
                {"category": b, "metric": "NPS", "value": float(rb["nps"])},
            ])

            fig_cmp = px.bar(
                cmp_df,
                x="metric",
                y="value",
                color="category",
                barmode="group",
                title=f"Compare Categories — {a} vs {b}",
            )
            fig_cmp.update_layout(xaxis_title="Metric", yaxis_title="Value")
            st.plotly_chart(fig_cmp, width="stretch")

    if st.session_state.compare_pair is None:
        # Top-N slice by selected metric (controlled via chat)
        top_n = int(st.session_state.top_n)
        top_metric = st.session_state.top_metric
        metric_labels = {"review_count": "Review Count", "nps": "NPS", "avg_rating": "Average Rating"}
        metric_label = metric_labels.get(top_metric, "Review Count")

        mdf_top = mdf.sort_values(top_metric, ascending=False).head(top_n)

        fig_top = px.bar(mdf_top, x="category", y=top_metric, title=f"Top {top_n} Categories by {metric_label}")
        fig_top.update_layout(xaxis_title="Category", yaxis_title=metric_label, xaxis_tickangle=-45)
        st.plotly_chart(fig_top, width="stretch")


    # Rating distribution: driven by plot_state["rating_dist_category"]
    cat = st.session_state.plot_state["rating_dist_category"]
    if cat is None:
        if st.session_state.compare_pair is not None:
            cat = st.session_state.compare_pair[0]
        else:
            cat = mdf.sort_values("review_count", ascending=False).iloc[0]["category"]

    sub = visible_df[(visible_df["category"] == cat)].dropna(subset=["rating"])
    fig_hist = px.histogram(sub, x="rating", nbins=5, title=f"Rating Distribution — {cat}")
    fig_hist.update_layout(xaxis_title="Rating", yaxis_title="Count")
    st.plotly_chart(fig_hist, width="stretch")


# Right: Chat
with right:
    st.header("Chat")

    # Scrollable container for chat history
    # Usually height=600px or so fits well next to graphs.
    chat_container = st.container(height=700)
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    if not allowed_categories:
        st.info("No categories available for chat.")
        st.stop()

    # Chat Input (Bottom)
    user_text = st.chat_input("Ask about ratings, NPS, reasons...")

    if user_text:
        st.session_state.chat_messages.append({"role": "user", "content": user_text})
        
        # Immediate feedback: Render the new user message in the container
        with chat_container:
            with st.chat_message("user"):
                st.write(user_text)
        
        # Logic processing
        assistant_text = "Sorry — I couldn't process that."
        router_out = None
        validated = None
        tool_result = None

        with SessionLocal() as db:
            if st.session_state.conversation_id is None:
                conv = get_or_create_conversation(db, user_id=st.session_state.user["id"], title="Streamlit chat")
                st.session_state.conversation_id = conv.id
            conversation_id = st.session_state.conversation_id
            user_id = st.session_state.user["id"]
            
            recent_msgs = st.session_state.chat_messages[-6:]
            recent_for_router = [{"role": m["role"], "content": m["content"]} for m in recent_msgs]

            try:
                router_out = route_tool(
                    user_message=user_text,
                    allowed_categories=allowed_categories,
                    recent_messages=recent_for_router,
                )
            except Exception as e:
                # Fallback
                router_out = {"tool": "general_query", "args": {"query_type": "summary_stats"}, "rationale": f"error: {e}"}

            validated = validate_tool_call(router_out, allowed_categories=set(allowed_categories))

            prev_state = {
                "compare_pair": st.session_state.compare_pair,
                "top_n": st.session_state.top_n,
                "top_metric": st.session_state.top_metric,
                "rating_dist_category": st.session_state.plot_state["rating_dist_category"],
            }

            tool_result = run_tool(
                db=db,
                visible_df=visible_df,
                tool=validated["tool"],
                args=validated["args"],
            )

            # Plot interactions
            if validated["tool"] == "rating_distribution":
                st.session_state.plot_state["rating_dist_category"] = validated["args"]["category"]

            if validated["tool"] == "metrics_top_categories":
                tn = validated["args"].get("top_n")
                if isinstance(tn, int):
                    tn = max(5, min(50, tn))
                    st.session_state.top_n = tn
                metric = validated["args"].get("metric")
                if metric in {"review_count", "nps", "avg_rating"}:
                    st.session_state.top_metric = metric

                st.session_state.compare_pair = None

            if validated["tool"] == "compare_categories":
                a = validated["args"]["category_a"]
                b = validated["args"]["category_b"]
                st.session_state.compare_pair = (a, b)
                st.session_state.plot_state["rating_dist_category"] = a


            assistant_text = write_response(
                user_message=user_text,
                tool_name=validated["tool"],
                tool_args=validated["args"],
                tool_result=tool_result,
                recent_messages=recent_for_router,
            )

            # UX overrides
            if validated["tool"] == "rating_distribution":
                cat = validated["args"]["category"]
                assistant_text = f"Updated the rating distribution for **{cat}** — check the plot on the left."

            if validated["tool"] == "metrics_top_categories":
                tn = validated["args"].get("top_n", st.session_state.top_n)
                metric = validated["args"].get("metric", st.session_state.top_metric)
                metric_labels = {"review_count": "Review Count", "nps": "NPS", "avg_rating": "Average Rating"}
                metric_label = metric_labels.get(metric, "Review Count")
                assistant_text = f"Updated to show Top {tn} categories by **{metric_label}** — check the plot on the left."

            if validated["tool"] == "compare_categories":
                a = validated["args"]["category_a"]
                b = validated["args"]["category_b"]
                assistant_text = f"Compared **{a}** vs **{b}** across review count, average rating, and NPS — check the chart on the left."

            assistant_text = apply_state_aware_response(
                tool=validated["tool"],
                args=validated["args"],
                prev_state=prev_state,
                assistant_text=assistant_text,
            )

            # Log trace
            log_trace(
                db,
                conversation_id=conversation_id,
                user_id=user_id,
                user_query=user_text,
                prompt_payload={"router": router_out},
                retrieval_payload={"tool": validated},
                response_payload={"assistant_text": assistant_text},
                plot_payload=None,
            )

        st.session_state.chat_messages.append({"role": "assistant", "content": assistant_text})
        
        # Rerun only for plot-updating tools to refresh the charts
        if validated and validated["tool"] in {"metrics_top_categories", "rating_distribution", "compare_categories"}:
            st.rerun()
        else:
            # st.rerun() is cleanest to show the new message in the history loop above.
            st.rerun()
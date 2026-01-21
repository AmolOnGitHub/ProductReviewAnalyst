import sys
from pathlib import Path
from dotenv import load_dotenv

# Path + .env setup
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


import streamlit as st
from sqlalchemy import text

from src.data_loader import load_reviews_csv
from src.user_service import authenticate_user, create_user
from src.db import init_db, SessionLocal, db_healthcheck
from src.analytics_df import build_analytics_df
from src.category_service import upsert_categories
from src.models import Category, User, UserCategoryAccess
from src.access_control import set_user_categories


# Streamlit Config
st.set_page_config(page_title="Review Analytics MVP", layout="wide")


# Session State 
if "user" not in st.session_state:
    st.session_state.user = None


# Login Gate
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


# Sidebar
st.sidebar.write(f"Logged in as: {st.session_state.user['email']}")
st.sidebar.write(f"Role: {st.session_state.user['role']}")

if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()


# Main Page
st.title("Review Analytics MVP — Dataset Check")
csv_path = st.text_input("CSV path", value="./data/amazon_products.csv")


# Admin only tools
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
                use_container_width=True,
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


# Dataset Preview
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
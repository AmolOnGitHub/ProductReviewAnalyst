# Streamlit Cloud Deployment Guide

This document explains how to deploy the Review Analytics system on **Streamlit Cloud** using **Supabase (Postgres)** as the backend database.

The deployment is designed so that:
- The **first admin account** is created manually in Supabase
- All further setup is handled through the app UI
- No secrets are committed to the repository

---

## 1. Create the Streamlit Cloud App

1. Go to https://streamlit.io/cloud
2. Click **New app**
3. Select:
   - **Repository** → your GitHub repo
   - **Branch** → `main`
   - **Main file path**:
     ```
     app/Analytics_Chat.py
     ```
4. Click **Deploy**

The app may fail initially — this is expected until secrets are configured.

---

## 2. Configure Streamlit Secrets

Open your app in Streamlit Cloud:

1. Click **⋮ → Settings → Secrets**
2. Add the following:

```toml
DATABASE_URL = "postgresql+psycopg://postgres.<project-ref>:<PASSWORD>@aws-<region>.pooler.supabase.com:6543/postgres"

GEMINI_API_KEY = "your_gemini_api_key"

SESSION_SECRET_KEY = "a-long-random-secret"
```

### Notes
- Do NOT include square brackets `[]` in the URL
- URL-encode the password if it contains special characters
- The `+psycopg` suffix is required (psycopg v3)
- `SESSION_SECRET_KEY` is required for cookie-based login persistence

Click **Save** — the app will automatically restart.

---

## 3. First-Time Initialization (One-Time)

After the app successfully loads:

1. Log in using the **admin account** created in Supabase
2. Open the **Admin Dashboard**
3. Click:
   - **Initialize DB tables**
   - **Ingest categories**

After this step:
- All required tables are created
- Categories are populated
- Analyst accounts can be created via the UI
- No further SQL access is needed

---

## 4. Verifying Deployment

Confirm the following:

- Login persists across refresh
- Analysts only see authorized categories
- Charts update based on chat instructions
- Gemini routing works
- Traces are logged correctly
- No database errors appear in logs

First load may be slow due to Supabase free-tier cold start (normal).

---

## Deployment Status

Once deployed and initialized, the system is fully operational and suitable for evaluation or demonstration.
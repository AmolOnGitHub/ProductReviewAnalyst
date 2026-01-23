# Supervised LLM-Based Review Analytics System

## Overview

This project is a supervised, tool-driven analytics system that allows users to explore large-scale customer review data using natural language, while maintaining strict control over correctness, access, and observability.

Instead of allowing a language model to freely answer questions over raw data, the system routes every user query through a deterministic tool layer. The LLM is used only for intent understanding and response synthesis, never for direct data access. All decisions are validated, access-controlled, and logged for traceability.

The system is implemented using Python, Streamlit, Supabase Postgres, and the Gemini API, and operates on an Amazon product reviews dataset.

Hosting:
- Streamlit for the app
- Supabase for the managed Postgres database

Available at: https://reviewanalyst-amolongh.streamlit.app/
---

## Problem Statement

Exploring large review datasets using traditional dashboards is rigid and unintuitive, while using a free-form LLM over data is unsafe and unreliable. Unconstrained LLMs can hallucinate statistics, bypass access control, or give misleading answers when queries are ambiguous.

The goal of this project is to enable **natural language analytics** over structured review data while preserving:

- Deterministic behavior
- Strong access control
- Explicit failure handling
- Full observability of LLM decisions

This system intentionally prioritizes correctness and transparency over flexibility.

---

## Core Design Principles

- **Tools over free-form generation**  
  The LLM never answers questions directly from data. It selects tools, which perform all computations deterministically.

- **Database as the source of truth**  
  All access control, authentication state, and category visibility are enforced at the data layer.

- **Fail safely and explicitly**  
  Invalid or unauthorized requests result in clear, user-facing refusals with safe fallbacks.

- **Observability by default**  
  Every LLM decision (routing, validation, fallback) is logged and inspectable via an admin trace viewer.

- **Scope control**  
  The system operates at the category level to keep reasoning stable, testable, and explainable.

---

## System Architecture

High-level flow:

```
User Query
   ↓
LLM Router (intent detection only)
   ↓
Validator (schema + access enforcement)
   ↓
Deterministic Tool Execution
   ↓
Response Synthesis (with LLM, given data from Tool Execution)
   ↓
Trace Logging (admin-visible)
```

The LLM is explicitly **not** allowed to:
- Query the database directly
- Perform arithmetic or aggregation
- Bypass access control
- Generate unsupported operations

---

## Supported Capabilities

- Top / bottom N categories by:
  - Review count
  - Average rating
  - Net Promoter Score (NPS)
- Rating distribution for a specific category
- Sentiment summaries grounded in review text
- Category-to-category comparison
- Stateful conversational refinement
- Deterministic plot updates
- Admin-only trace inspection

All visualizations are driven exclusively by validated tool outputs.

## Conversation Model

Currently, the system maintains **one active conversation per user session**. This simplifies state management and makes tool routing, access enforcement, and traceability easier to reason about.

The design can be easily extended to support **multiple concurrent conversations per user** by:
- Persisting multiple conversation records per user in the database
- Exposing a conversation selector in the UI
- Scoping router context and trace logs to a selected conversation ID

No architectural changes to the LLM router, validator, or tool layer are required for this extension.

---

## Authentication & Access Control Model

### Authentication
- Users authenticate via email/password
- Login state is persisted using **signed session cookies**
- Cookies store only a signed `user_id`
- User identity is revalidated against the database on every session restore
- Logout explicitly clears both session state and cookie

### Authorization
The system supports two roles:

- **Admin**
  - Full category access
  - User and category management
  - LLM trace inspection

- **Analyst**
  - Restricted to assigned categories
  - Cannot access or infer unauthorized data

Access control is enforced by:
- Query-time data filtering
- Cache versioning tied to access changes
- Access-aware refusals for invalid requests

Unauthorized queries never return partial or inferred data.

---

## Failure & Fallback Behavior

The system is designed to fail explicitly and safely:

- **Invalid queries** → Clear explanation + safe fallback
- **Unauthorized categories** → Access-aware refusal
- **Ambiguous intent** → Deterministic default behavior
- **LLM rate limits** → Bounded retries with backoff

Failures are given priority, not just treated as edge cases. This is very important when building systems around LLMs.

---

## Observability & Traceability

Every interaction logs:
- User query
- Router output
- Validated tool call
- Fallback rationale (if any)
- Tool results
- Final assistant response

Admins can inspect recent traces directly in the UI, making LLM behavior debuggable and auditable.

---

## Testing & Validation

The system was tested using a structured prompt suite covering:
- All supported tools
- Parameter coercion and bounds
- Access violations
- Fallback scenarios
- Retry and resilience behavior
- Ambiguous and malformed inputs

Testing focused on correctness, safety, and predictable behavior.

---

## What This Project Intentionally Does NOT Do

- **Item-level recommendations**  
  Category-level analytics were chosen to avoid large discrete search spaces and unstable intent resolution.

- **Time-series trend analysis**  
  The dataset lacks sufficient temporal resolution for meaningful trend modeling.

- **Embeddings or RAG pipelines**  
  Out of scope for the problem; would increase complexity without improving core guarantees.

- **Learning-to-rank or ML models**  
  Deterministic aggregation was preferred for transparency.

These omissions are deliberate design choices.

---

## Dataset & Tech Stack

- **Dataset:** Amazon Product Reviews (Kaggle)
- **Backend:** Python, Supabase Postgres, SQLAlchemy
- **Frontend:** Streamlit
- **Hosting:** Streamlit, Supabase
- **LLM:** Gemini (via API)
- **Visualization:** Plotly

Environment variables required:
```
GEMINI_API_KEY=your_api_key_here
SESSION_SECRET=your_session_secret
```

---

## Future Work

- Item-level retrieval layered under categories
- Automated evaluation harness for routing accuracy
- Deployment hardening and monitoring

---

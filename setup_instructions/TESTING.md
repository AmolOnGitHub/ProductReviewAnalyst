# Testing & Validation Guide

This document describes how to test the capabilities, safety properties, and failure handling of the Supervised LLM-Based Review Analytics System.

The goal of testing is not just correctness, but **predictability, access safety, and observability**.

---

## 1. Authentication & Session Persistence

### 1.1 Login Persistence
**Steps**
1. Log in as any user
2. Refresh the browser page

**Expected**
- User remains logged in
- Session is restored via signed cookie
- No re-login prompt is shown

---

### 1.2 Logout Behavior
**Steps**
1. Click `Logout`
2. Refresh the page

**Expected**
- User is logged out
- Login screen is shown
- Session cookie is cleared

---

## 2. Access Control Enforcement

### 2.1 Analyst Category Restriction
**Precondition**
- Analyst is assigned access to only a subset of categories

**Prompt**
```
Show the rating distribution for <unauthorized_category>
```

**Expected**
- Request is refused
- Assistant falls back to a safe alternative (e.g. top categories)
- No partial or inferred data is shown

---

### 2.2 Access-Aware Fallback Messaging
**Prompt**
```
Tell me about sentiment in <unauthorized_category>
```

**Expected**
- User is informed the request cannot be fulfilled
- System does not hallucinate or approximate results
- A safe fallback view is shown instead

---

## 3. Tool Routing Accuracy

### 3.1 Top Categories (Default Metric)
**Prompt**
```
Show me the top categories
```

**Expected**
- Tool selected: `metrics_top_categories`
- Metric defaults to review count
- Bar chart updates accordingly

---

### 3.2 Top Categories by Metric
**Prompt**
```
Show me the top 10 categories by NPS
```

**Expected**
- Tool selected: `metrics_top_categories`
- Metric = `nps`
- Top-N updated to 10
- Chart updates deterministically

---

### 3.3 Bottom Categories
**Prompt**
```
Show me the bottom 5 categories by average rating
```

**Expected**
- Tool selected: `metrics_top_categories`
- Metric = `avg_rating`
- Sorted ascending
- Chart reflects bottom categories

---

## 4. Rating Distribution

### 4.1 Valid Category
**Prompt**
```
Show the rating distribution for Electronics
```

**Expected**
- Tool selected: `rating_distribution`
- Histogram updates for Electronics
- Assistant confirms plot update

---

## 5. Sentiment Analysis

### 5.1 Sentiment Summary
**Prompt**
```
Why do customers like Electronics?
```

**Expected**
- Tool selected: `sentiment_summary`
- Output grounded in actual review text
- No hallucinated complaints or praise

---

### 5.2 Max Reviews Control
**Prompt**
```
Analyze sentiment for Kindle using 20 reviews
```

**Expected**
- max_reviews is capped and validated
- Gemini calls respect limits
- Output is deterministic

---

## 6. Category Comparison

### 6.1 Valid Comparison
**Prompt**
```
Compare Electronics and Home Audio
```

**Expected**
- Tool selected: `compare_categories`
- Output includes metrics for both categories
- Assistant explains differences clearly

---

### 6.2 Invalid Comparison
**Prompt**
```
Compare Electronics with Electronics
```

**Expected**
- System detects invalid comparison
- Falls back to rating distribution for Electronics
- Assistant explains why comparison was not possible

---

## 7. General Queries

### 7.1 Count Categories
**Prompt**
```
How many categories are there?
```

**Expected**
- Tool selected: `general_query`
- Returns total categories and review count

---

### 7.2 List Categories
**Prompt**
```
List all available categories
```

**Expected**
- Category list is access-filtered
- No unauthorized categories appear

---

## 8. Failure & Fallback Handling

### 8.1 Ambiguous Prompt
**Prompt**
```
Tell me something interesting
```

**Expected**
- Intent is ambiguous
- System falls back to summary statistics
- Assistant explains the fallback behavior

---

### 8.2 Invalid Tool Request
**Prompt**
```
Train a model on these reviews
```

**Expected**
- Unsupported request
- Safe fallback
- Clear explanation that the action is not supported

---

## 9. LLM Rate Limit Resilience

### 9.1 Rate Limit Simulation
**Steps**
- Temporarily reduce Gemini quota or simulate failures

**Expected**
- Requests are retried with backoff
- System does not crash
- User receives a graceful error if retries are exhausted

---

## 10. Observability & Traces (Admin Only)

### 10.1 Trace Inspection
**Steps**
1. Log in as Admin
2. Ask several queries
3. Open trace viewer

**Expected**
- Each interaction logs:
  - User query
  - Router output
  - Validated tool
  - Tool result
  - Assistant response
- Fallback rationale is visible when applicable

---

## Summary

This testing plan validates not only correctness, but also:
- Safety
- Access enforcement
- Deterministic behavior
- LLM supervision
- Production-oriented design

The system is intentionally tested against failure modes, not just happy paths.
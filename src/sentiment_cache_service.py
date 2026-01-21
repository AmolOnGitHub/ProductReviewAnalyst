from __future__ import annotations

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from src.models import ReviewSentimentCache
from src.llm.sentiment import analyze_reviews_batch, text_hash
from src.llm.gemini_client import MODEL_NAME


def get_cached_many(db: Session, hashes: List[str]) -> Dict[str, ReviewSentimentCache]:
    if not hashes:
        return {}
    rows = db.query(ReviewSentimentCache).filter(ReviewSentimentCache.text_hash.in_(hashes)).all()
    return {r.text_hash: r for r in rows} # type: ignore


def upsert_cache_row(
    db: Session,
    *,
    h: str,
    model: str,
    sentiment: str,
    reasons: list[str],
    latency_ms: int | None,
) -> None:
    stmt = insert(ReviewSentimentCache).values(
        text_hash=h,
        model=model,
        sentiment=sentiment,
        reasons=reasons,
        latency_ms=latency_ms,
    )

    # If text_hash already exists, update the row
    stmt = stmt.on_conflict_do_update(
        index_elements=[ReviewSentimentCache.text_hash],
        set_={
            "model": model,
            "sentiment": sentiment,
            "reasons": reasons,
            "latency_ms": latency_ms,
        },
    )

    db.execute(stmt)


def analyze_reviews_with_cache(
    db: Session,
    reviews: List[str],
    *,
    max_reviews: int = 50,
    batch_size: int = 10,
    timeout_s: float = 15.0,
) -> Dict[str, Any]:
    """
    Returns aggregated sentiment distribution + top reasons.
    Uses DB cache per review hash and batches uncached reviews.
    """
    from collections import Counter

    # truncate to cost control
    clean = []
    seen = set()
    for r in reviews:
        if not isinstance(r, str):
            continue
        rr = r.strip()
        if not rr:
            continue
        h = text_hash(rr)
        if h in seen:
            continue
        seen.add(h)
        clean.append(rr)
        if len(clean) >= max_reviews:
            break

    reviews = clean
    hashes = [text_hash(r) for r in reviews]

    cached = get_cached_many(db, hashes)

    sentiments = Counter()
    reasons = Counter()

    # Collect uncached indexes
    uncached_items = []
    for i, r in enumerate(reviews):
        h = hashes[i]
        if h in cached:
            row = cached[h]
            sentiments[row.sentiment] += 1
            for rr in (row.reasons or []):
                if isinstance(rr, str) and rr.strip():
                    reasons[rr.strip().lower()] += 1
        else:
            uncached_items.append((i, r))


    # Batch LLM calls for uncached
    newly_cached = 0
    for start in range(0, len(uncached_items), batch_size):
        chunk = uncached_items[start : start + batch_size]
        chunk_texts = [t for _, t in chunk]

        t0 = __import__("time").perf_counter()
        outputs = analyze_reviews_batch(chunk_texts, timeout_s=timeout_s)
        latency_ms = int((__import__("time").perf_counter() - t0) * 1000)

        # Map outputs by idx within chunk
        out_by_idx = {o["idx"]: o for o in outputs if isinstance(o, dict) and "idx" in o}

        for local_idx, (global_idx, text) in enumerate(chunk):
            h = hashes[global_idx]
            o = out_by_idx.get(local_idx)

            # Fail closed on missing result
            sentiment = "neutral"
            rs: list[str] = []

            if isinstance(o, dict):
                s = o.get("sentiment")
                if s in {"positive", "negative", "neutral"}:
                    sentiment = s

                rlist = o.get("reasons")
                if isinstance(rlist, list):
                    rs = [r for r in rlist if isinstance(r, str)]

            upsert_cache_row(
                db,
                h=h,
                model=MODEL_NAME,
                sentiment=sentiment,
                reasons=rs[:3],
                latency_ms=latency_ms,
            )

            sentiments[sentiment] += 1
            for rr in rs:
                if rr.strip():
                    reasons[rr.strip().lower()] += 1

        db.commit()

    return {
        "review_count_analyzed": sum(sentiments.values()),
        "sentiment_distribution": dict(sentiments),
        "top_reasons": reasons.most_common(10),
        "new_cache_rows": newly_cached,
        "cache_hits": len(reviews) - len(uncached_items),
    }
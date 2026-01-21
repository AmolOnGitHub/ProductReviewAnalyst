from __future__ import annotations

from typing import Dict, Any, List
import json
import random
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from google.genai import types

from src.llm.gemini_client import get_client, MODEL_NAME


_ALLOWED = {"positive", "negative", "neutral"}

SYSTEM_INSTRUCTION = (
    "You analyze customer reviews.\n"
    "Return ONLY valid JSON.\n"
    "For each review, output an object:\n"
    '{"idx": <int>, "sentiment": "positive|negative|neutral", "reasons": ["phrase", ...]}\n'
    "Rules:\n"
    "- reasons: up to 3 short noun phrases (2–5 words)\n"
    "- no full sentences\n"
    "- no punctuation\n"
    "- return a JSON array of objects\n"
)

# ---- latency stats (console) ----
_CALLS = 0
_TOTAL_LAT_S = 0.0


def _avg_latency_s() -> float:
    return (_TOTAL_LAT_S / _CALLS) if _CALLS else 0.0


def text_hash(review_text: str) -> str:
    # normalize lightly (don’t over-normalize; keep stable)
    t = (review_text or "").strip().lower()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _is_retryable_error(e: Exception) -> bool:
    msg = str(e).lower()
    return (
        "429" in msg
        or "resource_exhausted" in msg
        or ("rate" in msg and "limit" in msg)
        or "quota" in msg
        or "503" in msg
        or "unavailable" in msg
        or "deadline" in msg
        or "timeout" in msg
    )


def _sleep_backoff(attempt: int, *, base_delay_s: float, max_delay_s: float) -> None:
    delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
    delay *= (0.7 + 0.6 * random.random())  # jitter
    time.sleep(delay)


def _generate_with_timeout(call_fn, timeout_s: float):
    """
    Hard timeout wrapper. If the SDK hangs, we bail out.
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(call_fn)
        try:
            return fut.result(timeout=timeout_s)
        except FuturesTimeout:
            raise TimeoutError(f"LLM call exceeded timeout {timeout_s}s")


def analyze_reviews_batch(
    texts: List[str],
    *,
    timeout_s: float = 15.0,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
    max_delay_s: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    One LLM call that analyzes multiple reviews.
    Returns list of: {"idx": int, "sentiment": str, "reasons": list[str]}
    Indices correspond to input order in this batch.
    """
    global _CALLS, _TOTAL_LAT_S

    # Keep only non-empty strings, but preserve index mapping
    indexed = [(i, t) for i, t in enumerate(texts) if isinstance(t, str) and t.strip()]
    if not indexed:
        return []

    client = get_client()

    # Build prompt with numbered reviews
    lines = []
    for idx, t in indexed:
        # truncate very long reviews to control token cost / latency
        tt = t.strip()
        if len(tt) > 1200:
            tt = tt[:1200]
        lines.append(f"[{idx}] {tt}")

    prompt = (
        "Analyze the following reviews.\n"
        "Return ONLY JSON array. Each element must include idx, sentiment, reasons.\n\n"
        + "\n\n".join(lines)
    )

    def _do_call():
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                max_output_tokens=600,
                response_mime_type="application/json",
            ),
        )

    t0 = time.perf_counter()
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = _generate_with_timeout(_do_call, timeout_s=timeout_s)
            raw = (resp.text or "").strip()

            latency = time.perf_counter() - t0
            _CALLS += 1
            _TOTAL_LAT_S += latency
            print(f"[gemini][batch] latency={latency:.3f}s avg={_avg_latency_s():.3f}s calls={_CALLS}")
            print(f"[gemini][batch] raw_preview={(raw.replace(chr(10),' ')[:400])}")

            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                # sometimes returns a single object; wrap it
                parsed = [parsed]

            out: List[Dict[str, Any]] = []
            for obj in parsed:
                if not isinstance(obj, dict):
                    continue
                idx = obj.get("idx")
                sentiment = obj.get("sentiment")
                reasons = obj.get("reasons")

                if not isinstance(idx, int):
                    continue
                if sentiment not in _ALLOWED:
                    continue
                if not isinstance(reasons, list):
                    reasons = []

                clean_reasons = []
                for r in reasons:
                    if isinstance(r, str):
                        rr = r.strip()
                        if rr:
                            clean_reasons.append(rr)
                out.append({"idx": idx, "sentiment": sentiment, "reasons": clean_reasons[:3]})

            return out

        except Exception as e:
            last_exc = e
            print(f"[gemini][batch] error attempt {attempt}/{max_attempts}: {e}")
            if attempt == max_attempts or not _is_retryable_error(e):
                break
            _sleep_backoff(attempt, base_delay_s=base_delay_s, max_delay_s=max_delay_s)

    # Fail closed: return empty => caller marks as neutral
    return []
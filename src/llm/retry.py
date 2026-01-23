from __future__ import annotations
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

RETRYABLE_ERROR_KEYWORDS = [
    "resource_exhausted",
    "429",
    "rate limit",
    "timeout",
    "temporarily unavailable",
    "connection",
    "network",
]


def call_with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 5,
    base_delay_s: float = 0.8,
    max_delay_s: float = 10.0,
) -> T:
    """
    Exponential backoff with jitter.
    Retries on exceptions (we'll scope it at call site to 429 only if desired).
    """
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            # exponential backoff + jitter
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay = delay * (0.7 + 0.6 * random.random())  # jitter in [0.7, 1.3]
            time.sleep(delay)

    # If we exhausted retries, raise the last exception
    assert last_exc is not None
    raise last_exc


def is_retryable_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(keyword in msg for keyword in RETRYABLE_ERROR_KEYWORDS)


def with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_s: float = 0.5,
) -> T:
    """
    Executes fn() with bounded exponential backoff for retryable errors only.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            attempt += 1
            if attempt >= max_attempts or not is_retryable_error(exc):
                raise

            sleep_time = base_delay_s * (2 ** (attempt - 1))
            sleep_time += random.uniform(0, 0.2)
            time.sleep(sleep_time)

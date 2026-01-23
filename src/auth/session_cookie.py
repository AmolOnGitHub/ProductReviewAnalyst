from __future__ import annotations

import json
import os
from http.cookies import SimpleCookie
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "elm_session"
COOKIE_SALT = "elm_session"
DEFAULT_MAX_AGE_DAYS = 7


def _cookie_max_age_seconds() -> int:
    raw_days = os.getenv("SESSION_COOKIE_MAX_AGE_DAYS", str(DEFAULT_MAX_AGE_DAYS))
    try:
        days = int(raw_days)
    except ValueError:
        days = DEFAULT_MAX_AGE_DAYS
    days = max(1, days)
    return days * 24 * 60 * 60


def _get_serializer() -> URLSafeTimedSerializer | None:
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        return None
    return URLSafeTimedSerializer(secret, salt=COOKIE_SALT)


def _use_secure_cookie() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}


def _read_cookie_value() -> str | None:
    try:
        import streamlit as st
    except Exception:
        return None

    headers = getattr(getattr(st, "context", None), "headers", None)
    if not headers:
        return None

    cookie_header = headers.get("cookie") or headers.get("Cookie")
    if not cookie_header:
        return None

    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(COOKIE_NAME)
    if not morsel:
        return None
    return morsel.value


def _write_cookie(value: str, *, max_age_s: int, expires: str | None = None) -> None:
    try:
        import streamlit.components.v1 as components
    except Exception:
        return

    parts = [
        f"{COOKIE_NAME}={value}",
        "Path=/",
        "SameSite=Lax",
        f"Max-Age={max_age_s}",
    ]
    if expires:
        parts.append(f"Expires={expires}")
    if _use_secure_cookie():
        parts.append("Secure")

    cookie_str = "; ".join(parts)
    components.html(
        f"<script>document.cookie = {json.dumps(cookie_str)};</script>",
        height=0,
        width=0,
    )


def set_session_cookie(user_id: int) -> None:
    serializer = _get_serializer()
    if serializer is None:
        return
    token = serializer.dumps({"user_id": int(user_id)})
    _write_cookie(token, max_age_s=_cookie_max_age_seconds())


def get_user_id_from_cookie() -> Optional[int]:
    serializer = _get_serializer()
    if serializer is None:
        return None

    token = _read_cookie_value()
    if not token:
        return None

    try:
        payload = serializer.loads(token, max_age=_cookie_max_age_seconds())
    except (BadSignature, SignatureExpired):
        clear_session_cookie()
        return None

    if isinstance(payload, dict):
        user_id = payload.get("user_id")
        if isinstance(user_id, int):
            return user_id
        if isinstance(user_id, str) and user_id.isdigit():
            return int(user_id)

    clear_session_cookie()
    return None


def clear_session_cookie() -> None:
    _write_cookie("", max_age_s=0, expires="Thu, 01 Jan 1970 00:00:00 GMT")

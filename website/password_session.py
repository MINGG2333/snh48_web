"""Shared password-session policy for private pages (2026-11-09).

Default policy:
- HttpOnly, Secure, SameSite=Strict, path-limited cookie.
- 60-minute session (`PASSWORD_SESSION_MAX_AGE_SECONDS`), no browser storage.
- The signing secret lives in process memory only. A website restart invalidates
  every cookie, so deploys force a fresh password entry.
- A stale/unknown cookie means "login expired": return 401 and do NOT count it as
  a wrong-password attempt. Only a submitted password (POST /login or a password
  request header) consumes the anti-brute-force budget.
- Each password group uses its own rate-limit budget.

Pages whose content includes ``<audio>``/``<video>`` may instead use
memory-only password + short-lived signed media URLs (see ``flip_cards_api.py``).
"""

from __future__ import annotations

import hashlib
import hmac
import os

from website import config as cfg

# Process-local secret: every restart rotates it on purpose.
COOKIE_SECRET = os.urandom(32)


def cookie_max_age() -> int:
    return cfg.PASSWORD_SESSION_MAX_AGE_SECONDS


def cookie_token(password: str, *, context: str = "") -> str:
    """Return an HMAC token for an HttpOnly cookie (never the raw password)."""
    message = f"{context}:{password}".encode("utf-8")
    return hmac.new(COOKIE_SECRET, message, hashlib.sha256).hexdigest()


def cookie_matches(
    supplied_cookie: str | None,
    password: str,
    *,
    context: str = "",
) -> bool:
    if not supplied_cookie or not password:
        return False
    return hmac.compare_digest(supplied_cookie, cookie_token(password, context=context))


def password_was_submitted(*values: str | None) -> bool:
    """True when the request actually supplied a password (a real guess).

    A stale/empty cookie must not be treated as a wrong-password attempt.
    """
    return any(value for value in values)

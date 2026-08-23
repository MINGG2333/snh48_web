"""Short-lived server-side challenges used by public write endpoints."""

from __future__ import annotations

import secrets
import threading
import time


_TTL_SECONDS = 10 * 60
_MAX_CHALLENGES = 5000
_LOCK = threading.Lock()
_CHALLENGES: dict[str, tuple[str, float]] = {}


def issue_challenge(answer: str, *, ttl_seconds: int = _TTL_SECONDS) -> str:
    """Return an opaque one-use token whose answer never reaches the client."""
    now = time.time()
    with _LOCK:
        expired = [token for token, (_value, expires_at) in _CHALLENGES.items() if expires_at <= now]
        for token in expired:
            _CHALLENGES.pop(token, None)
        if len(_CHALLENGES) >= _MAX_CHALLENGES:
            oldest = min(_CHALLENGES, key=lambda token: _CHALLENGES[token][1])
            _CHALLENGES.pop(oldest, None)
        token = secrets.token_urlsafe(24)
        _CHALLENGES[token] = (str(answer), now + max(1, int(ttl_seconds)))
        return token


def consume_challenge(token: str, answer: str) -> bool:
    """Consume a challenge exactly once and compare its answer."""
    token = str(token or "").strip()
    answer = str(answer or "").strip()
    if not token or not answer:
        return False
    now = time.time()
    with _LOCK:
        stored = _CHALLENGES.pop(token, None)
    if not stored or stored[1] <= now:
        return False
    return secrets.compare_digest(stored[0], answer)

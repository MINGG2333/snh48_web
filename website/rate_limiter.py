"""
Rate limiting for Q&A API to prevent abuse and control API costs.

Provides multiple layers of protection:
  1. IP-based sliding-window rate limit
  2. Per-user minimum cooldown between questions
  3. Per-user daily question quota
  4. Per-user concurrent task limit
  5. Password verification rate limit (anti brute-force)
  6. IP-based daily question quota (persistent, survives restart)  # CHANGED

All limits are in-memory (single-process FastAPI), reset on server restart.
All configurable via environment variables / .env file.
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Optional, Set, Tuple

from fastapi import HTTPException, Request, status

from website import config as cfg
from website.logging_setup import log_api_error

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Sliding-Window Rate Limiter (per IP)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SlidingWindowLimiter:
    """
    Per-IP rate limiter using a sliding window of timestamps.

    Tracks request timestamps for each IP address and rejects requests
    that exceed the configured limit within the time window.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: Dict[str, "Deque[float]"] = defaultdict(deque)

    def _cleanup(self, key: str, now: float) -> None:
        """Remove timestamps outside the window."""
        dq = self._records[key]
        cutoff = now - self.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()
        if not dq:
            self._records.pop(key, None)

    def reset(self, key: str) -> None:
        """Clear all records for *key* (e.g. after successful password verification)."""
        self._records.pop(key, None)

    def check(self, key: str) -> Tuple[bool, int]:
        """
        Check if an action from *key* is allowed under the rate limit.

        Returns (allowed, current_count_within_window).
        """
        now = time.time()
        self._cleanup(key, now)
        current = len(self._records[key])
        if current >= self.max_requests:
            return False, current
        self._records[key].append(now)
        return True, current + 1

    @property
    def stats(self) -> dict:
        """Return current statistics for debugging / monitoring."""
        return {
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "active_keys": len(self._records),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Global Rate Limiter Instances
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# How many QA questions per IP per time window
qa_ip_limiter = SlidingWindowLimiter(
    max_requests=cfg.QA_RATE_LIMIT_PER_WINDOW,
    window_seconds=cfg.QA_RATE_LIMIT_WINDOW_SECONDS,
)

# How many password attempts per IP per time window (anti brute-force)
password_limiter = SlidingWindowLimiter(
    max_requests=cfg.PASSWORD_RATE_LIMIT_PER_WINDOW,
    window_seconds=cfg.PASSWORD_RATE_LIMIT_WINDOW_SECONDS,
)

# ── Generic public-endpoint rate limiters (anti-abuse) ────────────────────

# Scroller admin login brute-force protection
scroller_login_limiter = SlidingWindowLimiter(
    max_requests=cfg.SCROLLER_LOGIN_MAX_PER_WINDOW,
    window_seconds=cfg.SCROLLER_LOGIN_WINDOW_SECONDS,
)

# Email archive submission anti-spam
email_submit_limiter = SlidingWindowLimiter(
    max_requests=cfg.EMAIL_SUBMIT_MAX_PER_WINDOW,
    window_seconds=cfg.EMAIL_SUBMIT_WINDOW_SECONDS,
)

# Track event anti-flood (prevents forged event injection)
track_event_limiter = SlidingWindowLimiter(
    max_requests=cfg.TRACK_EVENT_MAX_PER_WINDOW,
    window_seconds=cfg.TRACK_EVENT_WINDOW_SECONDS,
)

# Complaint submission anti-spam
complaint_limiter = SlidingWindowLimiter(
    max_requests=cfg.COMPLAINT_MAX_PER_WINDOW,
    window_seconds=cfg.COMPLAINT_WINDOW_SECONDS,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Per-User State (tracked by client_id)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Cooldown: last question timestamp per client_id
_last_question_time: Dict[str, float] = {}

# Daily quota: (date_string, count) per client_id
_daily_usage: Dict[str, Tuple[str, int]] = {}

# Concurrent tasks: set of "client_id:task_id" strings
_active_tasks: Set[str] = set()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  IP Extraction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting reverse-proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  QA Question Rate-Limit Checks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def check_qa_rate_limit(ip: str) -> int:
    """
    Check IP-based QA rate limit.

    Returns current count within window.
    Raises HTTP 429 if exceeded.
    """
    allowed, count = qa_ip_limiter.check(ip)
    if not allowed:
        log_api_error(ip, "/api/qa/ask", f"IP级限速拒绝（{count}/{cfg.QA_RATE_LIMIT_PER_WINDOW}）")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
        )
    return count


def check_user_cooldown(client_id: str) -> None:
    """
    Enforce minimum interval between two questions from the same user.

    Raises HTTP 429 if the user asks too quickly.
    """
    now = time.time()
    last = _last_question_time.get(client_id)
    if last is not None:
        elapsed = now - last
        if elapsed < cfg.QA_USER_COOLDOWN_SECONDS:
            remaining = int(cfg.QA_USER_COOLDOWN_SECONDS - elapsed)
            log_api_error(
                client_id, "/api/qa/ask",
                f"用户冷却拒绝（还需等待 {remaining}s）",
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                f"提问过于频繁，请稍后再试"
            ),
            )
    _last_question_time[client_id] = now


def check_daily_quota(client_id: str) -> None:
    """
    Enforce per-user daily question quota.

    Raises HTTP 429 if the user has exceeded their daily limit.
    """
    today = time.strftime("%Y-%m-%d")
    record = _daily_usage.get(client_id)
    if record and record[0] == today:
        if record[1] >= cfg.QA_DAILY_QUOTA_PER_USER:
            log_api_error(
                client_id, "/api/qa/ask",
                f"日配额拒绝（{record[1]}/{cfg.QA_DAILY_QUOTA_PER_USER}）",
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日提问次数已达上限，请明天再试",
            )
        # Increment count
        _daily_usage[client_id] = (today, record[1] + 1)
    else:
        # First question today for this user
        _daily_usage[client_id] = (today, 1)


def check_concurrent_tasks(client_id: str) -> None:
    """
    Enforce per-user concurrent task limit.

    Raises HTTP 429 if the user already has too many tasks in-flight.
    """
    user_task_count = sum(
        1 for key in _active_tasks if key.startswith(f"{client_id}:")
    )
    if user_task_count >= cfg.QA_MAX_CONCURRENT_PER_USER:
        log_api_error(
            client_id, "/api/qa/ask",
            f"并发限制拒绝（当前 {user_task_count} 个）",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="您有正在处理中的问题，请等待完成后再提问",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CHANGED: IP 每日限流（持久化，重启不丢失）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_IP_QUOTA_FILE = Path(__file__).resolve().parent / "data" / "ip_daily_quota.json"
_ip_quota_lock = threading.Lock()


def _load_ip_quota() -> dict:
    """从磁盘加载 IP 每日配额记录。"""
    try:
        if _IP_QUOTA_FILE.exists():
            with open(_IP_QUOTA_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_ip_quota(data: dict) -> None:
    """将 IP 每日配额记录写入磁盘。"""
    _IP_QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_IP_QUOTA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_today() -> str:
    """返回今天的日期字符串 YYYY-MM-DD。"""
    return time.strftime("%Y-%m-%d")


def check_daily_ip_quota(ip: str) -> None:
    """
    检查每个 IP 每天最多提问次数（持久化存储）。

    数据格式（JSON）：
    {
      "2026-05-23": {
        "ip1": 3,
        "ip2": 1
      },
      ...
    }

    每次调用会先清理过期日期（非今天）的记录，然后检查当前 IP 是否超额。
    """
    # CHANGED: IP 每日限流持久化检查
    today = _get_today()
    with _ip_quota_lock:
        data = _load_ip_quota()

        # 清理过期日期，只保留今天
        keys_to_delete = [k for k in data if k != today]
        for k in keys_to_delete:
            del data[k]

        today_data = data.get(today, {})
        current_count = today_data.get(ip, 0)

        if current_count >= cfg.QA_DAILY_IP_QUOTA:
            log_api_error(
                ip, "/api/qa/ask",
                f"IP 每日配额拒绝（{current_count}/{cfg.QA_DAILY_IP_QUOTA}）",
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今天提问次数已达上限，请明天再试",
            )

        # 更新计数并写回磁盘
        today_data[ip] = current_count + 1
        data[today] = today_data
        _save_ip_quota(data)


def get_ip_quota_stats() -> dict:
    """返回 IP 每日配额的统计信息。"""
    with _ip_quota_lock:
        data = _load_ip_quota()
    today = _get_today()
    today_data = data.get(today, {})
    return {
        "total_ips_today": len(today_data),
        "total_requests_today": sum(today_data.values()),
        "max_per_ip": cfg.QA_DAILY_IP_QUOTA,
    }


def check_all_qa_limits(ip: str, client_id: str) -> None:
    """Convenience: run all QA rate-limit checks at once."""
    check_qa_rate_limit(ip)
    check_user_cooldown(client_id)
    check_daily_quota(client_id)
    check_concurrent_tasks(client_id)
    check_daily_ip_quota(ip)  # CHANGED: IP 每日限流


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Task Lifecycle (track active tasks)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def register_task(task_id: str, client_id: str) -> None:
    """Mark a task as active (prevents concurrent task abuse)."""
    _active_tasks.add(f"{client_id}:{task_id}")


def unregister_task(task_id: str, client_id: str) -> None:
    """Remove a task from active set (call when task completes / errors)."""
    _active_tasks.discard(f"{client_id}:{task_id}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Password Brute-Force Protection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def check_password_rate_limit(ip: str) -> None:
    """
    Rate-limit password verification attempts (anti brute-force).

    Raises HTTP 429 if too many attempts from the same IP.
    """
    allowed, _ = password_limiter.check(ip)
    if not allowed:
        log_api_error(ip, "/api/qa/verify-password", "密码暴力破解限速拒绝")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="密码验证尝试过于频繁，请稍后再试",
        )


def reset_password_rate_limit(ip: str) -> None:
    """
    Clear password attempt records for *ip* after a successful login.

    This ensures that a legitimate user who enters the correct password
    does not continue to be penalized for earlier failed attempts.
    """
    password_limiter.reset(ip)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Monitoring / Debugging
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def get_rate_limiter_stats() -> dict:
    """Return current rate limiter state (for admin / monitoring)."""
    return {
        "qa_ip_limiter": qa_ip_limiter.stats,
        "password_limiter": password_limiter.stats,
        "scroller_login_limiter": scroller_login_limiter.stats,
        "email_submit_limiter": email_submit_limiter.stats,
        "track_event_limiter": track_event_limiter.stats,
        "complaint_limiter": complaint_limiter.stats,
        "active_tasks": len(_active_tasks),
        "tracked_users": {
            "with_cooldown": len(_last_question_time),
            "with_daily_quota": len(_daily_usage),
        },
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Public Endpoint Rate-Limit Checks (anti-abuse)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def check_scroller_login_limit(ip: str) -> None:
    """Rate-limit scroller admin login attempts (anti brute-force)."""
    allowed, count = scroller_login_limiter.check(ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后再试",
        )


def check_email_submit_limit(ip: str) -> None:
    """Rate-limit email archive submissions (anti-spam)."""
    allowed, count = email_submit_limiter.check(ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="邮箱提交过于频繁，请稍后再试",
        )


def check_track_event_limit(ip: str) -> None:
    """Rate-limit track event submissions (anti-event-flood)."""
    allowed, count = track_event_limiter.check(ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="事件提交过于频繁，请稍后再试",
        )


def check_complaint_limit(ip: str) -> None:
    """Rate-limit complaint submissions (anti-spam)."""
    allowed, count = complaint_limiter.check(ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="投诉提交过于频繁，请稍后再试",
        )

"""服务端操作审计：记录所有写操作（POST/PUT/PATCH/DELETE）。

目的：不依赖前端埋点，也能知道谁在什么时候改了什么。只记录元数据和参数摘要，
不记录响应正文；密码、Token、Cookie、密钥等字段一律脱敏。

输出：`<fan-hub>/private_handover/web_state/audit/user_actions-YYYYMM.jsonl`
（0664，站点用户可写；不进 Git）。
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = Path(
    os.getenv(
        "USER_AUDIT_DIR",
        str(PROJECT_ROOT.parent / "snh48-fan-hub" / "private_handover" / "web_state" / "audit"),
    )
)
BJ_TZ = timezone(timedelta(hours=8))
SENSITIVE = re.compile(r"(password|passwd|token|secret|cookie|authorization|api[_-]?key|private[_-]?key)", re.I)
SKIP_PATHS = (
    "/api/track/",
    "/api/room-messages/login",
    "/api/flip-cards/login",
    "/api/room-messages/verify",
    "/api/flip-cards/verify",
)
MAX_STR = 300
MAX_ITEMS = 30


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "..."
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:MAX_ITEMS]:
            if SENSITIVE.search(str(key)):
                out[str(key)[:60]] = "***"
            else:
                out[str(key)[:60]] = _sanitize(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth + 1) for item in list(value)[:MAX_ITEMS]]
    if isinstance(value, str):
        cleaned = "".join(ch for ch in value if ch == "\n" or ch >= " ")
        return cleaned[:MAX_STR]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_STR]


def should_skip(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in SKIP_PATHS)


def record(
    *,
    method: str,
    path: str,
    query: str,
    status: int,
    duration_ms: int,
    ip: str,
    user_agent: str,
    visitor_id: str,
    body: Any,
) -> None:
    now = datetime.now(BJ_TZ)
    entry = {
        "schema_version": 1,
        "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
        "method": method,
        "path": path,
        "query": (query or "")[:500],
        "status": int(status),
        "duration_ms": int(duration_ms),
        "ip": ip,
        "user_agent": (user_agent or "")[:300],
        "visitor_id": visitor_id,
        "body": _sanitize(body),
    }
    directory = DEFAULT_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"user_actions-{now.strftime('%Y%m')}.jsonl"
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with target.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(line)
            fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            os.chmod(target, 0o664)
        except OSError:
            pass
    except OSError:
        # 审计失败不能影响正常请求
        pass

"""Privacy-limited visitor observation helpers for the password-protected OB page.

The browser supplies a first-party ``visitor_id`` that represents one browser
profile.  It is not treated as a verified natural-person identity.  For page
views only, the server records the current IP address and a coarse device label
derived from the already-present User-Agent request header.  No city,
coordinates, GeoIP lookup, canvas data, fonts, GPU data, or other active device
fingerprinting is collected here.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


PAGE_VIEWS_FILENAME = "visitor_page_views.jsonl"

_VISITOR_ID_RE = re.compile(r"^visitor_[A-Za-z0-9_-]{8,96}$")
_CLIENT_ID_RE = re.compile(r"^user_[A-Za-z0-9_-]{4,96}$")
_WRITE_LOCK = threading.Lock()


def is_valid_visitor_id(value: Any) -> bool:
    """Return whether a client-supplied browser profile ID is safe to store."""
    return isinstance(value, str) and bool(_VISITOR_ID_RE.fullmatch(value))


def is_valid_client_id(value: Any) -> bool:
    """Return whether an anonymous session ID is safe for filename lookup."""
    return isinstance(value, str) and bool(_CLIENT_ID_RE.fullmatch(value))


def describe_user_agent(user_agent: str) -> dict[str, str]:
    """Reduce a User-Agent string to a non-unique device/browser description."""
    ua = (user_agent or "").strip()
    ua_lower = ua.lower()

    if "iphone" in ua_lower:
        device_type, operating_system = "手机", "iPhone"
    elif "ipad" in ua_lower:
        device_type, operating_system = "平板", "iPad"
    elif "android" in ua_lower:
        if "mobile" in ua_lower:
            device_type, operating_system = "手机", "Android"
        else:
            device_type, operating_system = "平板", "Android"
    elif "windows" in ua_lower:
        device_type, operating_system = "电脑", "Windows"
    elif "macintosh" in ua_lower or "mac os x" in ua_lower:
        device_type, operating_system = "电脑", "macOS"
    elif "linux" in ua_lower:
        device_type, operating_system = "电脑", "Linux"
    else:
        device_type, operating_system = "未知设备", "未知系统"

    if "micromessenger/" in ua_lower:
        browser = "微信内置浏览器"
    elif "htbrowser/" in ua_lower:
        browser = "华为浏览器"
    elif "edgios/" in ua_lower or "edga/" in ua_lower or "edg/" in ua_lower:
        browser = "Edge"
    elif "crios/" in ua_lower or "chrome/" in ua_lower:
        browser = "Chrome"
    elif "fxios/" in ua_lower or "firefox/" in ua_lower:
        browser = "Firefox"
    elif "safari/" in ua_lower and "version/" in ua_lower:
        browser = "Safari"
    else:
        browser = "未知浏览器"

    if operating_system in {"iPhone", "iPad"}:
        label = f"{operating_system} · {browser}"
    elif operating_system == "Android":
        label = f"Android {device_type} · {browser}"
    elif operating_system.startswith("未知"):
        label = browser if browser != "未知浏览器" else "未知设备"
    else:
        label = f"{operating_system} {device_type} · {browser}"

    return {
        "type": device_type,
        "os": operating_system,
        "browser": browser,
        "label": label,
    }


def record_page_view(
    session_dir: Path,
    *,
    visitor_id: str,
    client_id: str,
    ip: str,
    user_agent: str,
    page: str,
) -> dict[str, Any] | None:
    """Append one page-view observation and return the stored record.

    Invalid or missing browser/session IDs are ignored so forged public
    tracking requests cannot create unsafe identifiers or file references.
    """
    if not is_valid_visitor_id(visitor_id) or not is_valid_client_id(client_id):
        return None

    safe_page = str(page or "")[:512]
    if not safe_page.startswith("/"):
        safe_page = "/"

    now = datetime.now().astimezone()
    record = {
        "schema_version": 1,
        "timestamp": now.isoformat(timespec="seconds"),
        "time_str": now.strftime("%Y-%m-%d %H:%M:%S"),
        "visitor_id": visitor_id,
        "client_id": client_id,
        "page": safe_page,
        "ip": str(ip or "未知")[:128],
        "device": describe_user_agent(user_agent),
    }

    path = session_dir / PAGE_VIEWS_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
    except OSError:
        return None
    return record


def load_page_views(log_root: Path) -> list[dict[str, Any]]:
    """Load valid OB page-view observations across server sessions."""
    if not log_root.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for path in sorted(log_root.glob(f"session_*/{PAGE_VIEWS_FILENAME}")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            if not is_valid_visitor_id(record.get("visitor_id")):
                continue
            if not is_valid_client_id(record.get("client_id")):
                continue
            if not isinstance(record.get("device"), dict):
                continue
            records.append(record)

    records.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return records

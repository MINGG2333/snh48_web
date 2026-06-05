"""
Observation (OB) API Router

Provides data for the admin observation page, grouping user activity by IP.
IP addresses are NEVER sent to the frontend — only client_ids are exposed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from website import config as cfg
from website.logging_setup import get_session_dir, LOG_ROOT
from website.rate_limiter import get_client_ip

router = APIRouter(prefix="/api/ob", tags=["管理员观察页"])

IP_CLIENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "ip_clients.json"


async def verify_ob_password(x_ob_password: str = Header(None, alias="X-Ob-Password")):
    """Verify the OB page password."""
    if not cfg.OB_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="观察页未启用",
        )
    if not x_ob_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要密码",
        )
    # Constant-time comparison
    import hmac
    if not hmac.compare_digest(cfg.OB_PASSWORD, x_ob_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="密码错误",
        )
    return True


@router.get("/data")
def get_ob_data(_=Depends(verify_ob_password)):
    """
    Return user activity data grouped by IP (IPs NOT exposed to frontend).

    Returns:
      {
        "groups": [
          {
            "id": 0,
            "users": ["user_xxx", "user_yyy"],
            "notification_count": 3,
            "notifications": [              // notification event summaries
              { "event_id": "EVT-...", "time_str": "...", "type_label": "...", "event_idx": 5 }
            ],
            "events": [
              {
                "time_str": "2026-06-05 17:16:35",
                "type": "new_user",
                "type_label": "🆕 新用户登入",
                "client_id": "user_xxx",
                "page": "/",
                "detail": "...",
                "is_notification": true,
                "event_id": "EVT-..."
              },
              ...
            ]
          }
        ]
      }
    """
    if not IP_CLIENTS_FILE.exists():
        return {"groups": []}

    try:
        ip_clients = json.loads(IP_CLIENTS_FILE.read_text())
    except Exception:
        return {"groups": []}

    groups = []
    group_id = 0

    for ip, client_ids in ip_clients.items():
        events = []
        notifications = []
        notification_count = 0

        # Collect events from all notification_center.md files across sessions
        # and from per-user event files
        event_set: dict[str, dict] = {}  # dedup by event_id
        notif_idx = 0

        for session_dir in sorted(LOG_ROOT.iterdir(), reverse=True):
            if not session_dir.is_dir() or not session_dir.name.startswith("session_"):
                continue

            # Read notification_center.md for this session
            notif_path = session_dir / "notification_center.md"
            if notif_path.exists():
                _parse_notification_file(notif_path, client_ids, events, notifications)

            # Read per-user event files for non-notification events
            for cid in client_ids:
                user_md = session_dir / f"user_{cid}_events.md"
                if user_md.exists():
                    _parse_user_event_file(user_md, cid, events)

        # Sort events by time (newest first) and assign indices
        _sort_events(events)

        # Map notification event_ids to event indices
        for notif in notifications:
            for idx, ev in enumerate(events):
                if ev.get("event_id") == notif.get("event_id"):
                    notif["event_idx"] = idx
                    break

        if events:
            groups.append({
                "id": group_id,
                "users": client_ids,
                "notification_count": len(notifications),
                "notifications": notifications,
                "events": events,
            })
            group_id += 1

    # Sort groups by newest event first
    groups.sort(key=lambda g: g["events"][0]["time_str"] if g["events"] else "", reverse=True)

    return {"groups": groups}


def _sort_events(events: list[dict]):
    """Sort events by time (newest first), using event_id timestamp as fallback."""
    def _sort_key(ev: dict) -> str:
        return ev.get("time_str", ev.get("event_id", ""))
    events.sort(key=_sort_key, reverse=True)


def _parse_user_event_file(
    filepath: Path, client_id: str, events: list[dict]
):
    """Parse a per-user Markdown event file and append events to the list."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return

    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("| "):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Expected format:
        # | time_str | type_label | client_id | content | action_col |
        if len(parts) < 6:
            continue
        time_str = parts[1]
        type_label = parts[2]
        cid = parts[3].strip("`")
        content = parts[4]

        if cid != client_id:
            continue

        # Parse content for details
        page = ""
        question = ""
        detail = ""
        if "页面：" in content:
            page = content.split("页面：")[1].split(" →")[0].strip("`").strip()
        if "问题：" in content:
            question = content.split("问题：")[1].split(" →")[0].strip()
        if "详情：" in content:
            detail = content.split("详情：")[1].strip()

        event_type = _infer_event_type(type_label)
        event_id = f"EVT-{time_str.replace(' ', '').replace(':', '').replace('-', '')}-{client_id[:6]}"

        ev = {
            "time_str": time_str,
            "type": event_type,
            "type_label": type_label,
            "client_id": client_id,
            "page": page,
            "question": question,
            "detail": detail,
            "is_notification": False,
            "event_id": event_id,
        }
        # Avoid duplicates
        if not any(e.get("event_id") == event_id for e in events):
            events.append(ev)


def _parse_notification_file(
    filepath: Path, client_ids: list[str], events: list[dict], notifications: list[dict]
):
    """Parse a notification_center.md file and extract events for given client_ids."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return

    # Parse notification entries (--- separated, with ### EVT-... headers)
    entries = text.split("\n---\n")
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # Extract event_id from ### EVT-...
        event_id = ""
        for line in entry.split("\n"):
            line = line.strip()
            if line.startswith("### EVT-"):
                event_id = line.replace("### ", "").strip()
                break

        if not event_id:
            continue

        # Parse fields
        fields = {}
        for line in entry.split("\n"):
            line = line.strip()
            if line.startswith("| **") and "** |" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4:
                    key = parts[1].replace("**", "").strip()
                    val = parts[2].strip()
                    fields[key] = val

        cid = fields.get("用户", "").strip("`")
        if cid not in client_ids:
            continue

        time_str = fields.get("时间", "")
        type_label = fields.get("类型", "")
        page = fields.get("页面", "")
        question = fields.get("问题", "")
        detail = fields.get("详情", "")
        status = fields.get("处理状态", "⏳ 待处理")
        remark = fields.get("处理备注", "")

        event_type = _infer_event_type(type_label)

        ev = {
            "time_str": time_str,
            "type": event_type,
            "type_label": type_label,
            "client_id": cid,
            "page": page,
            "question": question,
            "detail": detail,
            "is_notification": True,
            "event_id": event_id,
            "status": status,
            "remark": remark,
        }

        # Avoid duplicates
        dup = False
        for existing in events:
            if existing.get("event_id") == event_id:
                dup = True
                break

        if not dup:
            events.append(ev)

        notifications.append({
            "event_id": event_id,
            "time_str": time_str,
            "type_label": type_label,
            "client_id": cid,
            "page": page,
            "question": question,
            "event_idx": 0,  # Will be updated after sorting
        })


def _infer_event_type(type_label: str) -> str:
    """Infer event type from label."""
    mapping = {
        "🆕": "new_user",
        "🤖": "qa_submit",
        "📧": "email_submit",
        "📋": "complaint_submit",
        "📄": "page_view",
        "🔑": "login_attempt",
        "👆": "click",
        "📸": "screenshot",
    }
    for emoji, etype in mapping.items():
        if emoji in type_label:
            return etype
    return "other"

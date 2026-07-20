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
from pydantic import BaseModel

from website import config as cfg
from website.logging_setup import LOG_ROOT
from website.rate_limiter import check_ob_login_limit, get_client_ip
from website.action_inbox import InboxError, list_requests, record_status

router = APIRouter(prefix="/api/ob", tags=["管理员观察页"])

IP_CLIENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "ip_clients.json"

# ── Read notifications tracking (persistent, survives restart) ─────────────
READ_NOTIFS_FILE = Path(__file__).resolve().parent.parent / "data" / "read_notifications.json"


def _ensure_read_notifs_file():
    """Create the read notifications tracking file if it doesn't exist."""
    READ_NOTIFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not READ_NOTIFS_FILE.exists():
        READ_NOTIFS_FILE.write_text("[]")


def _load_read_notifs() -> list[str]:
    """Load the list of read notification event IDs."""
    _ensure_read_notifs_file()
    try:
        return json.loads(READ_NOTIFS_FILE.read_text())
    except Exception:
        return []


def _save_read_notifs(event_ids: list[str]):
    """Save the list of read notification event IDs."""
    READ_NOTIFS_FILE.write_text(json.dumps(event_ids, ensure_ascii=False, indent=2))


class MarkReadRequest(BaseModel):
    event_id: str


class InboxStatusRequest(BaseModel):
    event_id: str
    status: str
    note: str = ""


async def verify_ob_password(
    request: Request,
    x_ob_password: str = Header(None, alias="X-Ob-Password"),
):
    """Verify the OB page password."""
    if not cfg.OB_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="观察页未启用",
        )
    if not x_ob_password:
        check_ob_login_limit(get_client_ip(request))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要密码",
        )
    # Constant-time comparison
    import hmac
    if not hmac.compare_digest(cfg.OB_PASSWORD, x_ob_password):
        check_ob_login_limit(get_client_ip(request))
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
    inbox = list_requests()
    if not IP_CLIENTS_FILE.exists():
        return {"groups": [], "inbox": inbox}

    try:
        ip_clients = json.loads(IP_CLIENTS_FILE.read_text())
    except Exception:
        return {"groups": [], "inbox": inbox}

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

    # Apply read status from tracking file
    read_ids = _load_read_notifs()
    for group in groups:
        for ev in group["events"]:
            if ev.get("is_notification") and ev.get("event_id") in read_ids:
                ev["status"] = "✅ 已处理"
        # Recalculate notification count
        group["notification_count"] = sum(
            1 for ev in group["events"]
            if ev.get("is_notification") and ev.get("status", "⏳ 待处理") == "⏳ 待处理"
        )
        # Also update notification list count
        group["notifications"] = [
            n for n in group["notifications"]
            if n.get("event_id") not in read_ids
        ]

    # Sort groups by newest event first
    groups.sort(key=lambda g: g["events"][0]["time_str"] if g["events"] else "", reverse=True)

    return {"groups": groups, "inbox": inbox}


@router.post("/mark-read")
def mark_notification_read(req: MarkReadRequest, _=Depends(verify_ob_password)):
    """Mark a notification as read (persistent)."""
    read_ids = _load_read_notifs()
    if req.event_id not in read_ids:
        read_ids.append(req.event_id)
        _save_read_notifs(read_ids)
    return {"success": True}


@router.post("/inbox/status")
def update_inbox_status(req: InboxStatusRequest, _=Depends(verify_ob_password)):
    """Append an immutable processing-status event for one shared request."""
    try:
        result = record_status(req.event_id.strip(), req.status.strip(), note=req.note.strip())
    except InboxError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "success": True,
        "event": result["event"],
        "replication_pending": not result["replicated"],
    }


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

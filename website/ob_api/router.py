"""
Observation (OB) API Router

Provides data for the password-protected admin observation page. New records
are grouped by a stable first-party browser profile ID so IP changes do not
split one browser into multiple members. Legacy records remain separate
session members because their physical device or natural-person identity
cannot be reliably reconstructed. A separate IP association layer groups
profile/session members for display convenience only; it never changes visitor
or session estimates.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Collection

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from website import config as cfg
from website.logging_setup import LOG_ROOT
from website.rate_limiter import check_ob_login_limit, get_client_ip
from website.action_inbox import InboxError, list_requests, record_status
from website.visitor_observation import is_valid_client_id, load_page_views

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


@router.get("/verify")
def verify_ob_login(response: Response, _=Depends(verify_ob_password)):
    """Verify the password without loading observation records."""
    response.headers["Cache-Control"] = "no-store"
    return {"verified": True}


@router.get("/data")
def get_ob_data(response: Response, _=Depends(verify_ob_password)):
    """Return browser/session records plus a display-only IP association layer."""
    response.headers["Cache-Control"] = "no-store"
    inbox = list_requests()
    ip_clients = _load_ip_clients()
    client_ips = _build_client_ip_index(ip_clients)
    page_views = load_page_views(LOG_ROOT)
    profile_specs = _build_profile_specs(page_views, client_ips)
    all_client_ids = {
        client_id
        for spec in profile_specs
        for client_id in spec["client_ids"]
    }
    activity_index = _load_activity_index(all_client_ids)

    groups: list[dict[str, Any]] = []
    for spec in profile_specs:
        client_ids = sorted(spec["client_ids"])
        events, notifications = _collect_activity(client_ids, activity_index)
        visits = sorted(
            spec["visits"],
            key=lambda item: str(item.get("timestamp", "")),
            reverse=True,
        )
        if not events and not visits:
            continue

        devices = _summarize_visits(visits, "device_label")
        networks = _summarize_visits(visits, "ip")
        observed_ips = {item["value"] for item in networks}
        for client_id in client_ids:
            for ip in client_ips.get(client_id, []):
                if ip in observed_ips:
                    continue
                networks.append({
                    "value": ip,
                    "visit_count": None,
                    "first_seen": "",
                    "last_seen": "",
                    "historical_only": True,
                })
                observed_ips.add(ip)

        recent_time = ""
        if events:
            recent_time = str(events[0].get("time_str", ""))
        if visits:
            recent_time = max(recent_time, str(visits[0].get("time_str", "")))

        groups.append({
            "visitor_id": spec["visitor_id"],
            "profile_label": _profile_label(spec["visitor_id"], devices, spec["is_legacy"]),
            "is_legacy": spec["is_legacy"],
            "users": client_ids,
            "devices": devices,
            "networks": networks,
            "visits": visits,
            "recent_time": recent_time,
            "notification_count": len(notifications),
            "notifications": notifications,
            "events": events,
        })

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

    groups.sort(key=lambda group: group["recent_time"], reverse=True)
    for group_id, group in enumerate(groups):
        group["id"] = group_id

    association_groups = _build_ip_association_groups(groups)

    stable_profiles = sum(1 for group in groups if not group["is_legacy"])
    legacy_sessions = len(groups) - stable_profiles
    return {
        "groups": groups,
        "association_groups": association_groups,
        "stats": {
            # Legacy session IDs are deliberately excluded from the visitor
            # estimate: counting them as people was the original overcounting
            # problem this redesign is intended to remove.
            "estimated_visitors": stable_profiles,
            "stable_profiles": stable_profiles,
            "legacy_sessions": legacy_sessions,
            "recorded_page_views": sum(len(group["visits"]) for group in groups),
        },
        "inbox": inbox,
    }


def _load_ip_clients() -> dict[str, list[str]]:
    if not IP_CLIENTS_FILE.exists():
        return {}
    try:
        raw = json.loads(IP_CLIENTS_FILE.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}

    result: dict[str, list[str]] = {}
    for ip, client_ids in raw.items():
        if not isinstance(ip, str) or not isinstance(client_ids, list):
            continue
        valid_ids = [item for item in client_ids if is_valid_client_id(item)]
        if valid_ids:
            result[ip] = valid_ids
    return result


def _build_client_ip_index(ip_clients: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for ip, client_ids in ip_clients.items():
        for client_id in client_ids:
            if ip not in result[client_id]:
                result[client_id].append(ip)
    return dict(result)


def _build_profile_specs(
    page_views: list[dict[str, Any]],
    client_ips: dict[str, list[str]],
) -> list[dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    claimed_client_ids: set[str] = set()
    # ``load_page_views`` returns newest first.  If site storage was cleared
    # while one tab session stayed open, the same client_id can briefly report
    # two visitor IDs.  Keep the newest visitor ID as the canonical owner so
    # its event history is never duplicated across two OB cards.
    canonical_visitor_by_client: dict[str, str] = {}
    for view in page_views:
        client_id = view["client_id"]
        visitor_id = canonical_visitor_by_client.setdefault(client_id, view["visitor_id"])
        device = view.get("device") or {}
        normalized_view = {
            "time_str": str(view.get("time_str", "")),
            "timestamp": str(view.get("timestamp", "")),
            "page": str(view.get("page", "")),
            "ip": str(view.get("ip", "未知")),
            "device_label": str(device.get("label", "未知设备")),
            "client_id": client_id,
        }
        profile = profiles.setdefault(visitor_id, {
            "visitor_id": visitor_id,
            "is_legacy": False,
            "client_ids": set(),
            "visits": [],
        })
        profile["client_ids"].add(client_id)
        profile["visits"].append(normalized_view)
        claimed_client_ids.add(client_id)

    for client_id in client_ips:
        if client_id in claimed_client_ids:
            continue
        legacy_id = f"legacy_{client_id}"
        profiles[legacy_id] = {
            "visitor_id": legacy_id,
            "is_legacy": True,
            "client_ids": {client_id},
            "visits": [],
        }
    return list(profiles.values())


def _summarize_visits(visits: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for visit in visits:
        value = str(visit.get(field, "") or "未知")
        time_str = str(visit.get("time_str", ""))
        item = summary.setdefault(value, {
            "value": value,
            "visit_count": 0,
            "first_seen": time_str,
            "last_seen": time_str,
            "historical_only": False,
        })
        item["visit_count"] += 1
        if time_str:
            item["first_seen"] = min(item["first_seen"] or time_str, time_str)
            item["last_seen"] = max(item["last_seen"] or time_str, time_str)
    return sorted(
        summary.values(),
        key=lambda item: (str(item["last_seen"]), str(item["value"])),
        reverse=True,
    )


def _profile_label(visitor_id: str, devices: list[dict[str, Any]], is_legacy: bool) -> str:
    if is_legacy:
        client_id = visitor_id.removeprefix("legacy_")
        return f"旧会话 · {client_id}"
    device = devices[0]["value"] if devices else "浏览器档案"
    return f"{device} · 档案尾码 {visitor_id[-8:]}"


def _build_ip_association_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build display-only connected components from exact shared IP values.

    Nodes are the existing browser-profile or legacy-session groups. An edge
    means two nodes have observed the same IP; this layer does not alter the
    underlying groups or any visitor/session statistics. ``historical_only``
    is retained so old-session links cannot be mistaken for per-visit data.
    """
    if not groups:
        return []

    group_by_id = {int(group["id"]): group for group in groups}
    parent = {group_id: group_id for group_id in group_by_id}

    def find(group_id: int) -> int:
        root = group_id
        while parent[root] != root:
            root = parent[root]
        while parent[group_id] != group_id:
            next_id = parent[group_id]
            parent[group_id] = root
            group_id = next_id
        return root

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    ip_members: dict[str, set[int]] = defaultdict(set)
    ip_details: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for group_id, group in group_by_id.items():
        for network in group.get("networks") or []:
            value = str(network.get("value", "")).strip()
            if not value or value == "未知":
                continue
            ip_members[value].add(group_id)
            ip_details[(group_id, value)].append(network)

    for member_ids in ip_members.values():
        ordered = sorted(member_ids)
        for member_id in ordered[1:]:
            union(ordered[0], member_id)

    components: dict[int, set[int]] = defaultdict(set)
    for group_id in group_by_id:
        components[find(group_id)].add(group_id)

    association_specs: list[dict[str, Any]] = []
    for member_ids in components.values():
        ordered_members = sorted(
            member_ids,
            key=lambda group_id: str(group_by_id[group_id].get("recent_time", "")),
            reverse=True,
        )
        shared_ips = []
        for ip, linked_members in ip_members.items():
            component_members = linked_members & member_ids
            if len(component_members) < 2:
                continue
            details = [
                item
                for group_id in component_members
                for item in ip_details.get((group_id, ip), [])
            ]
            shared_ips.append({
                "value": ip,
                "member_ids": sorted(component_members),
                "historical_only": bool(details) and all(
                    bool(item.get("historical_only")) for item in details
                ),
            })
        shared_ips.sort(key=lambda item: str(item["value"]))

        member_groups = [group_by_id[group_id] for group_id in ordered_members]
        association_specs.append({
            "id": "ip_association_" + str(len(association_specs)),
            "member_group_ids": ordered_members,
            "shared_ips": shared_ips,
            "member_count": len(member_groups),
            "stable_profile_count": sum(
                1 for group in member_groups if not group["is_legacy"]
            ),
            "legacy_session_count": sum(
                1 for group in member_groups if group["is_legacy"]
            ),
            "visit_count": sum(len(group.get("visits") or []) for group in member_groups),
            "notification_count": sum(
                int(group.get("notification_count") or 0) for group in member_groups
            ),
            "recent_time": max(
                (str(group.get("recent_time", "")) for group in member_groups),
                default="",
            ),
        })

    association_specs.sort(
        key=lambda item: (
            str(item.get("recent_time", "")),
            len(item.get("shared_ips") or []),
        ),
        reverse=True,
    )
    for association_id, association in enumerate(association_specs):
        association["id"] = "ip_association_" + str(association_id)
    return association_specs


def _load_activity_index(
    target_client_ids: set[str],
) -> dict[str, tuple[list[dict], list[dict]]]:
    events_by_client: dict[str, list[dict]] = defaultdict(list)
    notifications_by_client: dict[str, list[dict]] = defaultdict(list)
    if not LOG_ROOT.is_dir():
        return {}

    for session_dir in sorted(LOG_ROOT.iterdir(), reverse=True):
        if not session_dir.is_dir() or not session_dir.name.startswith("session_"):
            continue

        notif_path = session_dir / "notification_center.md"
        if notif_path.exists():
            session_events: list[dict] = []
            session_notifications: list[dict] = []
            _parse_notification_file(
                notif_path,
                target_client_ids,
                session_events,
                session_notifications,
            )
            for event in session_events:
                events_by_client[event["client_id"]].append(event)
            for notification in session_notifications:
                notifications_by_client[notification["client_id"]].append(notification)

        for user_md in session_dir.glob("user_*_events.md"):
            name = user_md.name
            client_id = name[len("user_"):-len("_events.md")]
            if client_id not in target_client_ids:
                continue
            _parse_user_event_file(user_md, client_id, events_by_client[client_id])

    return {
        client_id: (events_by_client[client_id], notifications_by_client[client_id])
        for client_id in target_client_ids
    }


def _collect_activity(
    client_ids: list[str],
    activity_index: dict[str, tuple[list[dict], list[dict]]],
) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    notifications: list[dict] = []
    event_keys: set[tuple[str, str, str, str]] = set()
    notification_keys: set[tuple[str, str]] = set()
    for client_id in client_ids:
        client_events, client_notifications = activity_index.get(client_id, ([], []))
        for event in client_events:
            key = (
                str(event.get("event_id", "")),
                str(event.get("client_id", "")),
                str(event.get("type", "")),
                str(event.get("page", "")),
            )
            if key not in event_keys:
                events.append(dict(event))
                event_keys.add(key)
        for notification in client_notifications:
            key = (
                str(notification.get("event_id", "")),
                str(notification.get("client_id", "")),
            )
            if key not in notification_keys:
                notifications.append(dict(notification))
                notification_keys.add(key)

    _sort_events(events)
    for notification in notifications:
        for index, event in enumerate(events):
            if event.get("event_id") == notification.get("event_id"):
                notification["event_idx"] = index
                break
    return events, notifications


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
    filepath: Path,
    client_ids: Collection[str],
    events: list[dict],
    notifications: list[dict],
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

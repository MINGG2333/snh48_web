"""
User Behavior Tracking API Router

Provides an endpoint for the frontend tracker to send user behavior events.
Events are recorded to:
  - user_events.jsonl (machine-readable, all users mixed)
  - user_{client_id}_events.jsonl (machine-readable, per user)
  - user_{client_id}_events.md (human-readable, per user)
  - notification_center.md (for important events)
  - ip_clients.json (IP→client_id mapping, for admin observation page)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from website.logging_setup import get_session_dir
from website.user_events import record_user_event

router = APIRouter(prefix="/api/track", tags=["用户行为追踪"])

# ── IP ↔ Client mapping file (for admin OB page, never exposed to frontend) ──
IP_CLIENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "ip_clients.json"


def _ensure_ip_clients_file():
    """Create the IP→client mapping file if it doesn't exist."""
    IP_CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not IP_CLIENTS_FILE.exists():
        IP_CLIENTS_FILE.write_text("{}")


def _track_ip_to_client(ip: str, client_id: str):
    """Record IP→client_id mapping (never sent to frontend)."""
    _ensure_ip_clients_file()
    try:
        data = json.loads(IP_CLIENTS_FILE.read_text())
        if ip not in data:
            data[ip] = []
        if client_id not in data[ip]:
            data[ip].append(client_id)
        IP_CLIENTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass  # Silently fail — IP tracking is best-effort


def _extract_client_ip(request: Request, x_forwarded_for: Optional[str]) -> str:
    """Extract client IP from request, respecting reverse-proxy headers."""
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


class TrackEventRequest(BaseModel):
    client_id: str
    event_type: str
    data: dict[str, Any] = {}


# ── Events that should be pushed to notification center ────────────────────
# Only events that require admin attention are included.
# Other events (qa_complete, qa_timeout, login_attempt, screenshot, etc.)
# are recorded in user event logs but do NOT generate notifications.
NOTIFICATION_EVENTS = {
    "new_user",        # New user first visit
    "qa_submit",       # User asked a question
    "email_submit",    # User submitted email
    "complaint_submit", # User submitted complaint
}


@router.post("/event")
def track_event(
    req: TrackEventRequest,
    request: Request,
    x_forwarded_for: Optional[str] = Header(None, alias="X-Forwarded-For"),
):
    """
    Record a user behavior event sent from the frontend tracker.

    Events are logged to:
      - user_events.jsonl (machine-readable, all events)
      - user_{client_id}_events.jsonl/.md (per user)
      - notification_center.md (only important events like Q&A, email, etc.)
    """
    session_dir = get_session_dir()
    client_id = req.client_id

    # ── Track IP → client mapping (for admin OB page, never exposed) ────
    ip = _extract_client_ip(request, x_forwarded_for)
    _track_ip_to_client(ip, client_id)

    # ── Detect new user ──────────────────────────────────────────────────
    # A new user is detected when their per-user JSONL file doesn't exist yet.
    # This means this is the first event ever received from this client_id.
    user_jsonl_path = session_dir / f"user_{client_id}_events.jsonl"
    is_new_user = not user_jsonl_path.exists()

    # ── Determine if this event should be pushed to notification center ──
    # The server is the authority on what goes to notifications.
    # Frontend _push_to_notification override is intentionally ignored
    # to ensure consistent notification policy.
    push_to_notification = req.event_type in NOTIFICATION_EVENTS

    # ── Record the actual event ──────────────────────────────────────────
    record_user_event(
        session_dir=session_dir,
        client_id=client_id,
        event_type=req.event_type,
        event_data=req.data,
        push_to_notification=push_to_notification,
    )

    # ── If new user, also push a "new_user" notification ─────────────────
    if is_new_user:
        # The notification will include a clickable link to the user's event log
        user_log_file = f"user_{client_id}_events.md"
        record_user_event(
            session_dir=session_dir,
            client_id=client_id,
            event_type="new_user",
            event_data={
                "page": req.data.get("page", ""),
                "detail": f"新用户首次访问，操作记录见 [{user_log_file}]({user_log_file})",
                "user_log": user_log_file,
            },
            push_to_notification=True,
        )

    return {"success": True}

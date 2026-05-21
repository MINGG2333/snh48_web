"""
User Behavior Tracking API Router

Provides an endpoint for the frontend tracker to send user behavior events.
Events are recorded to:
  - user_events.jsonl (machine-readable, all users mixed)
  - user_{client_id}_events.jsonl (machine-readable, per user)
  - user_{client_id}_events.md (human-readable, per user)
  - notification_center.md (for important events)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from website.logging_setup import get_session_dir
from website.user_events import record_user_event

router = APIRouter(prefix="/api/track", tags=["用户行为追踪"])


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

    # Add IP info for security-relevant events
    if req.event_type in ("login_attempt", "complaint_submit"):
        ip = x_forwarded_for or request.client.host if request.client else "unknown"
        req.data["ip"] = ip

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

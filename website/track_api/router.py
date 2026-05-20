"""
User Behavior Tracking API Router

Provides an endpoint for the frontend tracker to send user behavior events.
Events are recorded to:
  - user_events.jsonl (machine-readable)
  - user_events.md (human-readable)
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
NOTIFICATION_EVENTS = {
    "qa_submit",       # User asked a question
    "qa_complete",     # User got an answer
    "qa_timeout",      # Question timed out
    "email_submit",    # User submitted email
    "complaint_submit", # User submitted complaint
    "login_attempt",   # Login attempt (successful or failed)
    "screenshot",      # User saved screenshot
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
      - user_events.md (human-readable, all events)
      - notification_center.md (only important events like Q&A, email, etc.)
    """
    session_dir = get_session_dir()
    client_id = req.client_id

    # Determine if this event should be pushed to notification center
    push_to_notification = req.event_type in NOTIFICATION_EVENTS

    # Check for _push_to_notification override from frontend
    if req.data.get("_push_to_notification"):
        push_to_notification = True
        # Remove the internal flag from data
        req.data.pop("_push_to_notification", None)

    # Add IP info for security-relevant events
    if req.event_type in ("login_attempt", "complaint_submit"):
        ip = x_forwarded_for or request.client.host if request.client else "unknown"
        req.data["ip"] = ip

    record_user_event(
        session_dir=session_dir,
        client_id=client_id,
        event_type=req.event_type,
        event_data=req.data,
        push_to_notification=push_to_notification,
    )

    return {"success": True}

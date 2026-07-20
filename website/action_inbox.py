"""Durable, idempotent inbox for cross-server user requests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from website import config as cfg
from website.shared_runtime_state import SharedStatePeerError, node_id, node_label, peer_command


EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
REQUEST_TYPES = {"complaint", "email_request"}
EVENT_TYPES = REQUEST_TYPES | {"status_update"}
VALID_STATUSES = {"pending", "processing", "resolved", "rejected"}


class InboxError(RuntimeError):
    """Inbox data is invalid or cannot be persisted."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")


def _events_dir() -> Path:
    return Path(cfg.ACTION_INBOX_ROOT) / "events"


def _outbox_dir() -> Path:
    return Path(cfg.SHARED_STATE_OUTBOX_ROOT) / "inbox"


def _event_path(event_id: str) -> Path:
    if not EVENT_ID_RE.fullmatch(event_id):
        raise InboxError("invalid inbox event id")
    return _events_dir() / f"{event_id}.json"


def _canonical(event: dict[str, Any]) -> bytes:
    return json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deterministic_request_id(prefix: str, payload: dict[str, Any]) -> str:
    """Return the same event id when a legacy row is imported more than once."""
    safe_prefix = re.sub(r"[^A-Za-z0-9]", "-", prefix).strip("-").upper() or "REQ"
    digest = hashlib.sha256(_canonical(payload)).hexdigest()[:24].upper()
    return f"{safe_prefix}-{digest}"


def _atomic_create(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return True


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def install_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise InboxError("inbox event must be an object")
    event_id = str(event.get("event_id") or "")
    path = _event_path(event_id)
    normalised = dict(event)
    normalised["schema_version"] = 1
    event_type = str(normalised.get("event_type") or "")
    origin = str(normalised.get("origin_node") or "")
    payload = normalised.get("payload")
    if event_type not in EVENT_TYPES:
        raise InboxError("unsupported inbox event type")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", origin):
        raise InboxError("invalid inbox origin node")
    normalised["origin_label"] = node_label(origin)
    if not isinstance(payload, dict):
        raise InboxError("inbox event payload must be an object")
    if event_type == "status_update":
        target = str(payload.get("target_event_id") or "")
        if not EVENT_ID_RE.fullmatch(target) or str(payload.get("status") or "") not in VALID_STATUSES:
            raise InboxError("invalid inbox status event")
    content = json.dumps(normalised, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if len(content) > 1024 * 1024:
        raise InboxError("inbox event is too large")
    created = _atomic_create(path, content)
    if not created:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InboxError("existing inbox event cannot be read") from exc
        if hashlib.sha256(_canonical(existing)).digest() != hashlib.sha256(_canonical(normalised)).digest():
            raise InboxError("inbox event id collision")
    return normalised


def record_request(
    event_type: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if event_type not in REQUEST_TYPES:
        raise InboxError("unsupported inbox request type")
    eid = event_id or f"REQ-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:12]}"
    event = {
        "schema_version": 1,
        "event_id": eid,
        "event_type": event_type,
        "created_at": created_at or _now(),
        "origin_node": node_id(),
        "origin_label": node_label(),
        "payload": payload,
    }
    install_event(event)
    replicated = _replicate_event(event)
    return {"event": event, "replicated": replicated}


def record_status(
    target_event_id: str,
    status: str,
    *,
    note: str = "",
    actor: str = "admin",
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise InboxError("invalid inbox status")
    if not _event_path(target_event_id).exists():
        raise InboxError("target inbox event does not exist")
    event_id = f"STS-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%f')}-{uuid.uuid4().hex[:10]}"
    event = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "status_update",
        "created_at": _now(),
        "origin_node": node_id(),
        "origin_label": node_label(),
        "payload": {
            "target_event_id": target_event_id,
            "status": status,
            "note": note[:1000],
            "actor": actor[:80],
        },
    }
    install_event(event)
    replicated = _replicate_event(event)
    return {"event": event, "replicated": replicated}


def _queue_event(event: dict[str, Any]) -> None:
    path = _outbox_dir() / f"{event['event_id']}.json"
    _atomic_replace(path, json.dumps(event, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")


def _replicate_event(event: dict[str, Any]) -> bool:
    if not cfg.SHARED_STATE_SYNC_ENABLED or not cfg.SHARED_STATE_PEER:
        return True
    # Persist before attempting SSH so a killed process cannot lose the
    # obligation to copy an already accepted request.
    _queue_event(event)
    try:
        peer_command("inbox-put", {"event": event})
    except SharedStatePeerError:
        return False
    (_outbox_dir() / f"{event['event_id']}.json").unlink(missing_ok=True)
    return True


def retry_inbox_outbox_once() -> dict[str, int]:
    stats = {"inbox_sent": 0, "inbox_failed": 0}
    root = _outbox_dir()
    if not root.exists() or not cfg.SHARED_STATE_SYNC_ENABLED or not cfg.SHARED_STATE_PEER:
        return stats
    for path in sorted(root.glob("*.json")):
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
            peer_command("inbox-put", {"event": event})
            path.unlink(missing_ok=True)
            stats["inbox_sent"] += 1
        except (OSError, json.JSONDecodeError, SharedStatePeerError):
            stats["inbox_failed"] += 1
    return stats


def list_requests() -> list[dict[str, Any]]:
    requests: dict[str, dict[str, Any]] = {}
    statuses: dict[str, dict[str, Any]] = {}
    for path in sorted(_events_dir().glob("*.json")) if _events_dir().exists() else []:
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        event_type = str(event.get("event_type") or "")
        if event_type in REQUEST_TYPES:
            requests[str(event.get("event_id") or "")] = event
        elif event_type == "status_update":
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            target = str(payload.get("target_event_id") or "")
            previous = statuses.get(target)
            current_key = (str(event.get("created_at") or ""), str(event.get("event_id") or ""))
            previous_key = (
                str(previous.get("created_at") or ""),
                str(previous.get("event_id") or ""),
            ) if previous else ("", "")
            if previous is None or current_key > previous_key:
                statuses[target] = event

    output: list[dict[str, Any]] = []
    for event_id, event in requests.items():
        item = dict(event)
        status_event = statuses.get(event_id)
        status_payload = status_event.get("payload") if status_event and isinstance(status_event.get("payload"), dict) else {}
        item["status"] = str(status_payload.get("status") or "pending")
        item["status_note"] = str(status_payload.get("note") or "")
        item["status_updated_at"] = str((status_event or {}).get("created_at") or "")
        item["status_origin_node"] = str((status_event or {}).get("origin_node") or "")
        item["status_origin_label"] = str((status_event or {}).get("origin_label") or "")
        output.append(item)
    output.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("event_id") or "")), reverse=True)
    return output

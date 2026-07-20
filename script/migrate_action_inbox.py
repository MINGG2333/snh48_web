#!/usr/bin/env python3
"""Import legacy complaints and email requests into the durable action inbox.

The command prints counts only and never prints complaint text or email values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from website import config as cfg
from website.action_inbox import deterministic_request_id, record_request
from website.shared_runtime_state import node_id, node_label


def _legacy_id(kind: str, source: str, record: dict[str, Any]) -> str:
    raw = json.dumps(
        {"kind": kind, "source": source, "record": record},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"MIG-{kind.upper()}-{hashlib.sha256(raw).hexdigest()[:24]}"


def _iter_jsonl(path: Path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line_number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield line_number, record


def _events() -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    complaint_dir = cfg.PROJECT_ROOT / "website" / "data" / "complaints"
    for path in sorted(complaint_dir.glob("complaints_*.jsonl")):
        for line_number, record in _iter_jsonl(path):
            event_id = str(record.get("ticket_id") or "") or _legacy_id(
                "complaint", f"{path.name}:{line_number}", record
            )
            output.append({
                "schema_version": 1,
                "event_id": event_id,
                "event_type": "complaint",
                "created_at": str(record.get("created_at") or ""),
                "origin_node": node_id(),
                "origin_label": node_label(),
                "payload": record,
            })

    log_root = cfg.PROJECT_ROOT / "website" / "data" / "interaction_logs"
    for path in sorted(log_root.glob("session_*/email_requests.jsonl")):
        for line_number, record in _iter_jsonl(path):
            output.append({
                "schema_version": 1,
                "event_id": deterministic_request_id("EMAIL", record),
                "event_type": "email_request",
                "created_at": str(record.get("timestamp") or ""),
                "origin_node": node_id(),
                "origin_label": node_label(),
                "payload": record,
            })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write and replicate imported events")
    args = parser.parse_args()
    events = _events()
    if not args.apply:
        print(json.dumps({"apply": False, "found": len(events)}, ensure_ascii=False))
        return 0
    installed = 0
    replicated = 0
    pending = 0
    for event in events:
        result = record_request(
            str(event["event_type"]),
            dict(event["payload"]),
            event_id=str(event["event_id"]),
            created_at=str(event["created_at"]),
        )
        installed += 1
        if result["replicated"]:
            replicated += 1
        else:
            pending += 1
    print(json.dumps({
        "apply": True,
        "found": len(events),
        "installed": installed,
        "replicated": replicated,
        "pending": pending,
        "origin_node": node_id(),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

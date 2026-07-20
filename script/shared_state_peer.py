#!/usr/bin/env python3
"""Restricted SSH entrypoint for shared runtime state replication."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from website import config as cfg
from website.action_inbox import install_event
from website.shared_runtime_state import (
    SharedStateError,
    apply_authoritative_mutation,
    install_replica,
)


def _read_payload() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise SharedStateError("request must be a JSON object")
    return value


def _load_mutators() -> None:
    # Imports register pure state mutators. They do not start the web app.
    import website.scroller_api.router  # noqa: F401
    import website.room_messages_api  # noqa: F401
    import website.score_gifts_api  # noqa: F401
    import website.memories_api  # noqa: F401


def main() -> int:
    if len(sys.argv) != 2:
        raise SharedStateError("exactly one command is required")
    command = sys.argv[1]
    payload = _read_payload()

    if command == "install-replica":
        if cfg.SHARED_STATE_SYNC_ENABLED and cfg.SHARED_STATE_IS_PRIMARY:
            raise SharedStateError("the authoritative node does not accept replica state")
        resource = str(payload.get("resource") or "")
        state = payload.get("state")
        installed = install_replica(resource, state, operation="peer_replica")
        response = {"ok": True, "revision": (installed.get("_state") or {}).get("revision", "")}
    elif command == "mutate":
        if cfg.SHARED_STATE_SYNC_ENABLED and not cfg.SHARED_STATE_IS_PRIMARY:
            raise SharedStateError("this server is not the authoritative shared-state node")
        _load_mutators()
        resource = str(payload.get("resource") or "")
        operation = str(payload.get("operation") or "")
        operation_id = str(payload.get("operation_id") or "")
        origin = str(payload.get("origin_node") or "")
        mutation_payload = payload.get("payload")
        if not operation_id or not origin or not isinstance(mutation_payload, dict):
            raise SharedStateError("mutation metadata is incomplete")
        response = {"ok": True} | apply_authoritative_mutation(
            resource,
            operation,
            mutation_payload,
            operation_id=operation_id,
            origin=origin,
        )
    elif command == "inbox-put":
        event = payload.get("event")
        installed = install_event(event)
        response = {"ok": True, "event_id": installed.get("event_id", "")}
    else:
        raise SharedStateError("unsupported shared-state command")

    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
        status_code = int(getattr(exc, "status_code", 503) or 503)
        sys.stderr.write(json.dumps(
            {"ok": False, "error": str(detail), "status_code": status_code},
            ensure_ascii=False,
        ) + "\n")
        raise SystemExit(1)

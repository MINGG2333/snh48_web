"""Versioned shared runtime state and cross-server replication helpers.

Runtime JSON is kept out of Git.  Tencent is the authoritative writer while
both websites may accept operations; replica operations are forwarded over the
existing SSH channel.  Every committed state has an immutable gzip snapshot.
"""

from __future__ import annotations

import fcntl
import gzip
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import threading
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from website import config as cfg


class SharedStateError(RuntimeError):
    """Base error for shared state operations."""


class SharedStatePeerError(SharedStateError):
    """The peer could not accept or return shared state."""

    def __init__(self, detail: str, status_code: int = 503):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


Mutator = Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]

_registry: dict[tuple[str, str], Mutator] = {}
_worker_started = False
_worker_lock = threading.Lock()
_worker_stop = threading.Event()
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
SAFE_NODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
REVISION_RE = re.compile(r"^\d{8}T\d{6}\.\d{6}Z-[a-z0-9_-]+-[a-f0-9]{12}$")


def register_mutator(resource: str, operation: str, mutator: Mutator) -> None:
    _registry[(resource, operation)] = mutator


def node_id() -> str:
    return cfg.SHARED_STATE_NODE_ID


def node_label(value: str | None = None) -> str:
    target = value or node_id()
    return cfg.SHARED_STATE_NODE_LABELS.get(target, target)


def resource_path(resource: str) -> Path:
    paths = {
        "scroller": Path(cfg.SCROLLER_TEXTS_PATH),
        "room_ignore": Path(cfg.ROOM_MESSAGES_IGNORE_PATH),
        "score_business": Path(cfg.SCORE_GIFTS_DATA_PATH).parent / "live_business_fulfillments.json",
        "memories": Path(cfg.MEMORIES_DATA_PATH),
    }
    try:
        return paths[resource]
    except KeyError as exc:
        raise SharedStateError(f"unknown shared state resource: {resource}") from exc


def default_document(resource: str) -> dict[str, Any]:
    defaults = {
        "scroller": {"version": 2, "texts": []},
        "room_ignore": {"version": 2, "ignored_batches": []},
        "score_business": {"version": 1, "records": {}},
        "memories": {"version": 1, "items": []},
    }
    return deepcopy(defaults[resource])


def normalise_document(resource: str, value: Any) -> dict[str, Any]:
    if resource == "scroller" and isinstance(value, list):
        value = {"version": 2, "texts": [str(item) for item in value]}
    if not isinstance(value, dict):
        value = default_document(resource)
    doc = deepcopy(value)
    if resource == "scroller" and not isinstance(doc.get("texts"), list):
        doc["texts"] = []
    elif resource == "room_ignore" and not isinstance(doc.get("ignored_batches"), list):
        doc["ignored_batches"] = []
    elif resource == "score_business" and not isinstance(doc.get("records"), dict):
        doc["records"] = {}
    elif resource == "memories" and not isinstance(doc.get("items"), list):
        doc["items"] = []
    return doc


def canonical_bytes(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def state_hash(doc: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


def load_document(resource: str) -> dict[str, Any]:
    path = resource_path(resource)
    if not path.exists():
        return default_document(resource)
    try:
        return normalise_document(resource, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise SharedStateError(f"failed to read {resource} state") from exc


@contextmanager
def resource_lock(resource: str) -> Iterator[None]:
    path = resource_path(resource)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_revision() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}-{node_id()}-{uuid.uuid4().hex[:12]}"


def _history_dir(resource: str) -> Path:
    return Path(cfg.SHARED_STATE_HISTORY_ROOT) / resource


def _operation_receipt_path(resource: str, operation_id: str) -> Path:
    return _history_dir(resource) / "operations" / f"{operation_id}.json"


def _atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_snapshot(resource: str, doc: dict[str, Any], operation: str) -> None:
    meta = doc.get("_state") if isinstance(doc.get("_state"), dict) else {}
    revision = str(meta.get("revision") or "")
    if not revision:
        return
    target = _history_dir(resource) / "snapshots" / f"{revision}.json.gz"
    if target.exists():
        return
    payload = {
        "schema_version": 1,
        "resource": resource,
        "revision": revision,
        "parent_revision": str(meta.get("parent_revision") or ""),
        "created_at": str(meta.get("updated_at") or _now()),
        "origin_node": str(meta.get("origin_node") or ""),
        "origin_label": node_label(str(meta.get("origin_node") or "")),
        "operation": str(meta.get("operation") or operation),
        "state_sha256": state_hash(doc),
        "state": doc,
    }
    compressed = gzip.compress(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n",
        compresslevel=6,
    )
    _atomic_write(target, compressed)


def _write_current(resource: str, doc: dict[str, Any]) -> None:
    content = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    _atomic_write(resource_path(resource), content)


def _commit_locked(
    resource: str,
    doc: dict[str, Any],
    *,
    operation: str,
    operation_id: str,
    origin: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    current = load_document(resource)
    parent = str((current.get("_state") or {}).get("revision") or "")
    committed = normalise_document(resource, doc)
    committed["updated_at"] = _now()
    committed["_state"] = {
        "revision": _new_revision(),
        "parent_revision": parent,
        "updated_at": committed["updated_at"],
        "origin_node": origin,
        "origin_label": node_label(origin),
        "operation": operation,
        "operation_id": operation_id,
    }
    # Persist the immutable history object first. If current-state replacement
    # then fails, an unreferenced snapshot is harmless; the opposite ordering
    # could expose a revision for which no recovery snapshot exists.
    _write_snapshot(resource, committed, operation)
    _write_current(resource, committed)
    receipt = {
        "operation_id": operation_id,
        "resource": resource,
        "operation": operation,
        "revision": committed["_state"]["revision"],
        "created_at": committed["updated_at"],
        "origin_node": origin,
        "origin_label": node_label(origin),
        "result": result,
    }
    _atomic_write(
        _operation_receipt_path(resource, operation_id),
        json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
    )
    return committed


def apply_authoritative_mutation(
    resource: str,
    operation: str,
    payload: dict[str, Any],
    *,
    operation_id: str,
    origin: str,
) -> dict[str, Any]:
    if not SAFE_ID_RE.fullmatch(operation_id):
        raise SharedStateError("invalid shared-state operation id")
    if not SAFE_NODE_RE.fullmatch(origin):
        raise SharedStateError("invalid shared-state origin node")
    mutator = _registry.get((resource, operation))
    if mutator is None:
        raise SharedStateError(f"unsupported mutation: {resource}/{operation}")
    with resource_lock(resource):
        receipt_path = _operation_receipt_path(resource, operation_id)
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            committed = load_document(resource)
            result = receipt.get("result") or {}
            duplicate = True
        else:
            current = load_document(resource)
            candidate, result = mutator(deepcopy(current), deepcopy(payload))
            committed = _commit_locked(
                resource,
                candidate,
                operation=operation,
                operation_id=operation_id,
                origin=origin,
                result=result,
            )
            duplicate = False
    replicated = _replicate_or_queue(resource, committed)
    return {
        "state": committed,
        "result": result,
        "duplicate": duplicate,
        "replicated": replicated,
    }


def execute_mutation(
    resource: str,
    operation: str,
    payload: dict[str, Any],
    *,
    operation_id: str | None = None,
) -> dict[str, Any]:
    op_id = operation_id or uuid.uuid4().hex
    if not cfg.SHARED_STATE_SYNC_ENABLED or cfg.SHARED_STATE_IS_PRIMARY:
        return apply_authoritative_mutation(
            resource,
            operation,
            payload,
            operation_id=op_id,
            origin=node_id(),
        )
    response = peer_command(
        "mutate",
        {
            "resource": resource,
            "operation": operation,
            "operation_id": op_id,
            "origin_node": node_id(),
            "payload": payload,
        },
    )
    state = normalise_document(resource, response.get("state"))
    install_replica(resource, state, operation=f"replica:{operation}")
    return response


def install_replica(resource: str, doc: dict[str, Any], *, operation: str = "replica") -> dict[str, Any]:
    incoming = normalise_document(resource, doc)
    incoming_revision = str((incoming.get("_state") or {}).get("revision") or "")
    meta = incoming.get("_state") if isinstance(incoming.get("_state"), dict) else {}
    incoming_origin = str(meta.get("origin_node") or "")
    if not REVISION_RE.fullmatch(incoming_revision) or not SAFE_NODE_RE.fullmatch(incoming_origin):
        raise SharedStateError("replica state metadata is invalid")
    with resource_lock(resource):
        current = load_document(resource)
        current_revision = str((current.get("_state") or {}).get("revision") or "")
        if current_revision == incoming_revision:
            _write_snapshot(resource, incoming, operation)
            return current
        # Revisions are generated only by the authoritative node and start
        # with a UTC timestamp. A delayed outbox entry must never roll a
        # replica back after a newer revision has already arrived.
        if current_revision and incoming_revision < current_revision:
            _write_snapshot(resource, incoming, operation)
            return current
        _write_snapshot(resource, incoming, operation)
        _write_current(resource, incoming)
    return incoming


def _outbox_path(resource: str, revision: str) -> Path:
    return Path(cfg.SHARED_STATE_OUTBOX_ROOT) / "state" / resource / f"{revision}.json"


def _queue_replica(resource: str, doc: dict[str, Any]) -> None:
    revision = str((doc.get("_state") or {}).get("revision") or "")
    if not revision:
        return
    payload = {"resource": resource, "state": doc}
    _atomic_write(
        _outbox_path(resource, revision),
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
    )


def _replicate_or_queue(resource: str, doc: dict[str, Any]) -> bool:
    if not cfg.SHARED_STATE_SYNC_ENABLED or not cfg.SHARED_STATE_PEER:
        return True
    revision = str((doc.get("_state") or {}).get("revision") or "")
    # Write-ahead outbox: a process crash or timeout during SSH must leave a
    # durable item for the next worker pass.
    _queue_replica(resource, doc)
    try:
        peer_command("install-replica", {"resource": resource, "state": doc})
    except SharedStatePeerError:
        return False
    if revision:
        _outbox_path(resource, revision).unlink(missing_ok=True)
    return True


def peer_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not cfg.SHARED_STATE_PEER:
        raise SharedStatePeerError("shared-state peer is not configured")
    remote = (
        f"cd {shlex.quote(str(cfg.SHARED_STATE_REMOTE_ROOT))} && "
        f"{shlex.quote(str(cfg.SHARED_STATE_REMOTE_PYTHON))} "
        f"script/shared_state_peer.py {shlex.quote(command)}"
    )
    cmd = [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "LogLevel=ERROR",
        "-o",
        f"ConnectTimeout={cfg.SHARED_STATE_CONNECT_TIMEOUT_SECONDS}",
        cfg.SHARED_STATE_PEER,
        remote,
    ]
    try:
        result = subprocess.run(
            cmd,
            input=json.dumps(payload, ensure_ascii=False),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=cfg.SHARED_STATE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SharedStatePeerError("shared-state peer timed out") from exc
    if result.returncode != 0:
        raw = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        try:
            error = json.loads(raw.splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            error = {}
        detail = str(error.get("error") or raw or "shared-state peer failed")[:300]
        status_code = int(error.get("status_code") or 503)
        raise SharedStatePeerError(detail, status_code=status_code)
    try:
        response = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SharedStatePeerError("shared-state peer returned invalid JSON") from exc
    if not isinstance(response, dict) or not response.get("ok", False):
        raise SharedStatePeerError(
            str(response.get("error") or "shared-state peer rejected request"),
            status_code=int(response.get("status_code") or 503),
        )
    return response


def retry_outbox_once() -> dict[str, int]:
    stats = {"state_sent": 0, "state_failed": 0}
    root = Path(cfg.SHARED_STATE_OUTBOX_ROOT) / "state"
    if root.exists() and cfg.SHARED_STATE_SYNC_ENABLED and cfg.SHARED_STATE_PEER:
        for path in sorted(root.glob("*/*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                peer_command("install-replica", payload)
                path.unlink(missing_ok=True)
                stats["state_sent"] += 1
            except (OSError, json.JSONDecodeError, SharedStatePeerError):
                stats["state_failed"] += 1
    try:
        from website.action_inbox import retry_inbox_outbox_once

        inbox_stats = retry_inbox_outbox_once()
        stats.update(inbox_stats)
    except Exception:
        stats["inbox_failed"] = stats.get("inbox_failed", 0) + 1
    return stats


def _worker() -> None:
    while not _worker_stop.is_set():
        retry_outbox_once()
        _worker_stop.wait(max(10, cfg.SHARED_STATE_RETRY_INTERVAL_SECONDS))


def start_replication_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        threading.Thread(target=_worker, name="shared-state-replication", daemon=True).start()


def list_history(resource: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((_history_dir(resource) / "snapshots").glob("*.json.gz"), reverse=True):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
            entries.append({key: payload.get(key) for key in (
                "resource", "revision", "parent_revision", "created_at", "origin_node", "origin_label", "operation", "state_sha256"
            )})
            if limit is not None and len(entries) >= max(1, limit):
                break
        except (OSError, json.JSONDecodeError):
            continue
    return entries


def ensure_baseline(resource: str) -> dict[str, Any]:
    """Create the first immutable revision for legacy unversioned JSON."""
    with resource_lock(resource):
        current = load_document(resource)
        revision = str((current.get("_state") or {}).get("revision") or "")
        if revision:
            _write_snapshot(resource, current, "baseline_check")
            committed = current
        else:
            operation_id = f"baseline-{resource}-{state_hash(current)[:24]}"
            committed = _commit_locked(
                resource,
                current,
                operation="baseline_migration",
                operation_id=operation_id,
                origin=node_id(),
                result={"baseline": True},
            )
    _replicate_or_queue(resource, committed)
    return committed


def replicate_current(resource: str) -> bool:
    """Replicate the current authoritative revision or queue it durably."""
    current = load_document(resource)
    if not str((current.get("_state") or {}).get("revision") or ""):
        current = ensure_baseline(resource)
    return _replicate_or_queue(resource, current)


def restore_revision(resource: str, revision: str) -> dict[str, Any]:
    if cfg.SHARED_STATE_SYNC_ENABLED and not cfg.SHARED_STATE_IS_PRIMARY:
        raise SharedStateError("history restore must be run on the primary node")
    if not REVISION_RE.fullmatch(revision):
        raise SharedStateError("invalid revision")
    path = _history_dir(resource) / "snapshots" / f"{revision}.json.gz"
    if not path.exists():
        raise SharedStateError("revision not found")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    state = normalise_document(resource, payload.get("state"))

    def restore_mutator(_current: dict[str, Any], _payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        restored = deepcopy(state)
        restored.pop("_state", None)
        return restored, {"restored_revision": revision}

    register_mutator(resource, f"restore:{revision}", restore_mutator)
    return execute_mutation(resource, f"restore:{revision}", {})

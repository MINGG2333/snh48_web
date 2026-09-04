#!/usr/bin/env python3
"""Collect website capacity metrics and safely archive rotated Nginx logs."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


LOG_LINE_RE = re.compile(
    r"\[(?P<timestamp>[^]]+)\] \"(?P<request>[^\"]*)\" "
    r"(?P<status>\d{3}) (?P<bytes>\d+)"
)
DEFAULT_THRESHOLD_BYTES = 1024**3
DEFAULT_METRICS_ROOT = "/var/lib/snh48-web/metrics"
DEFAULT_ARCHIVE_ROOT = "/var/lib/snh48-web/log-archives"
DEFAULT_ACTION_INBOX_ROOT = "/home/snh48_web/website/data/action_inbox"
DEFAULT_SHARED_OUTBOX_ROOT = "/home/snh48_web/website/data/shared_state_outbox"
DEFAULT_SERVICE_NAMES = {
    "tencent": "snh48-web.service",
    "aliyun": "snh48-aliyun.service",
}
# Keep observability labels identical to website/config.py so the same event
# has byte-for-byte identical metadata on both nodes after replication.
DEFAULT_NODE_LABELS = {"tencent": "腾讯云 cjy.plus", "aliyun": "阿里云 cjy.我爱你"}


class ObservabilityError(RuntimeError):
    def __init__(self, message: str, *, code: str = "archive_failed", total_bytes: int = 0):
        super().__init__(message)
        self.code = code
        self.total_bytes = max(0, int(total_bytes))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temp_path, mode)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def expand_patterns(patterns: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        for path in Path("/").glob(pattern.lstrip("/")) if pattern.startswith("/") else Path(".").glob(pattern):
            try:
                if path.is_file() and not path.is_symlink():
                    files.add(path.resolve())
            except OSError:
                continue
    return sorted(files)


def parse_log_line(line: str) -> tuple[str, str, int, int, bool] | None:
    match = LOG_LINE_RE.search(line)
    if not match:
        return None
    try:
        timestamp = datetime.strptime(match.group("timestamp"), "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None
    request = match.group("request").split()
    path = urlsplit(request[1]).path if len(request) >= 2 else ""
    is_page = (
        len(request) >= 2
        and request[0] == "GET"
        and not path.startswith(("/api/", "/static/", "/image-proxy/"))
        and not path.startswith("/favicon")
    )
    day = timestamp.date().isoformat()
    hour = timestamp.strftime("%Y-%m-%dT%H:00:00%z")
    return day, hour, int(match.group("status")), int(match.group("bytes")), is_page


def empty_day() -> dict[str, Any]:
    return {"requests": 0, "page_requests": 0, "response_bytes": 0, "status_counts": {}, "hourly": {}}


def merge_log_line(daily: dict[str, Any], parsed: tuple[str, str, int, int, bool]) -> None:
    day, hour, status, response_bytes, is_page = parsed
    item = daily.setdefault(day, empty_day())
    item["requests"] += 1
    item["page_requests"] += int(is_page)
    item["response_bytes"] += response_bytes
    status_counts = item.setdefault("status_counts", {})
    key = str(status)
    status_counts[key] = int(status_counts.get(key, 0)) + 1
    hourly = item.setdefault("hourly", {})
    bucket = hourly.setdefault(
        hour,
        {"requests": 0, "page_requests": 0, "response_bytes": 0, "status_counts": {}},
    )
    bucket["requests"] += 1
    bucket["page_requests"] += int(is_page)
    bucket["response_bytes"] += response_bytes
    bucket_status_counts = bucket.setdefault("status_counts", {})
    bucket_status_counts[key] = int(bucket_status_counts.get(key, 0)) + 1


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def read_incremental_access_logs(
    paths: list[Path], state: dict[str, Any], daily: dict[str, Any]
) -> int:
    file_state = state.setdefault("access_files", {})
    parse_errors = int(state.get("parse_errors", 0))
    for path in paths:
        try:
            file_stat = path.stat()
        except OSError:
            continue
        key = str(path)
        signature = {"inode": file_stat.st_ino, "size": file_stat.st_size, "mtime_ns": file_stat.st_mtime_ns}
        old = file_state.get(key) or {}
        is_gzip = path.name.endswith(".gz")
        if is_gzip:
            if old.get("signature") == signature:
                continue
            try:
                handle = gzip.open(path, "rt", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with handle:
                for line in handle:
                    parsed = parse_log_line(line)
                    if parsed is None:
                        parse_errors += 1
                    else:
                        merge_log_line(daily, parsed)
            file_state[key] = {"signature": signature, "processed": True}
            continue

        offset = int(old.get("offset", 0)) if old.get("signature", {}).get("inode") == file_stat.st_ino else 0
        if offset > file_stat.st_size:
            offset = 0
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                for line in handle:
                    parsed = parse_log_line(line)
                    if parsed is None:
                        parse_errors += 1
                    else:
                        merge_log_line(daily, parsed)
                new_offset = handle.tell()
        except OSError:
            continue
        file_state[key] = {"signature": signature, "offset": new_offset}
    state["parse_errors"] = parse_errors
    return parse_errors


def collect_visitor_counts(visitor_root: Path) -> dict[str, int]:
    visitors: dict[str, set[str]] = {}
    if not visitor_root.is_dir():
        return {}
    for path in sorted(visitor_root.glob("session_*/visitor_page_views.jsonl")):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                        visitor_id = str(item.get("visitor_id") or "")
                        timestamp = str(item.get("timestamp") or item.get("time_str") or "")
                        day = timestamp[:10]
                        if visitor_id and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                            visitors.setdefault(day, set()).add(visitor_id)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    return {day: len(values) for day, values in visitors.items()}


def read_cpu_ticks() -> tuple[int, int]:
    try:
        first = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
        values = [int(value) for value in first[1:]]
    except (OSError, IndexError, ValueError):
        return 0, 0
    return sum(values), values[3] if len(values) > 3 else 0


def read_disk_io() -> dict[str, int]:
    totals = {"read_sectors": 0, "written_sectors": 0, "io_ms": 0}
    try:
        lines = Path("/proc/diskstats").read_text(encoding="ascii").splitlines()
    except OSError:
        return totals
    selected = False
    for line in lines:
        fields = line.split()
        if len(fields) < 14:
            continue
        name = fields[2]
        if re.fullmatch(r"(?:sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)", name):
            selected = True
            totals["read_sectors"] += int(fields[5])
            totals["written_sectors"] += int(fields[9])
            totals["io_ms"] += int(fields[12])
    if selected:
        return totals
    return totals


def read_service_process_metrics(service_name: str | None) -> dict[str, Any]:
    """Read the web process RSS and lifetime high-water mark.

    System-wide snapshots run every five minutes and can miss a short QA
    startup spike. ``VmHWM`` is retained by the kernel for the lifetime of
    the service process, so a later snapshot still records that peak.
    """
    if not service_name:
        return {}
    try:
        result = subprocess.run(
            ["systemctl", "show", "--property=MainPID", "--value", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        pid = int((result.stdout or "").strip() or "0")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"service_name": service_name, "pid": 0}
    metrics: dict[str, Any] = {"service_name": service_name, "pid": pid}
    if pid <= 0:
        return metrics
    try:
        lines = Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        return metrics
    fields = {
        "VmRSS": "rss_bytes",
        "VmHWM": "hwm_bytes",
        "VmSwap": "swap_bytes",
        "VmSize": "vm_size_bytes",
        "Threads": "threads",
    }
    for line in lines:
        key, _, raw_value = line.partition(":")
        output_key = fields.get(key)
        if output_key is None:
            continue
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        if key != "Threads" and len(parts) > 1 and parts[1] == "kB":
            value *= 1024
        metrics[output_key] = value
    return metrics


def resource_snapshot(state: dict[str, Any], service_name: str | None = None) -> dict[str, Any]:
    total_ticks, idle_ticks = read_cpu_ticks()
    previous = state.get("cpu") or {}
    cpu_percent = None
    if total_ticks >= int(previous.get("total_ticks", 0)) and previous.get("total_ticks") is not None:
        total_delta = total_ticks - int(previous.get("total_ticks", 0))
        idle_delta = idle_ticks - int(previous.get("idle_ticks", 0))
        if total_delta > 0:
            cpu_percent = round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 2)
    state["cpu"] = {"total_ticks": total_ticks, "idle_ticks": idle_ticks}

    meminfo: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, _, value = line.partition(":")
            parts = value.strip().split()
            if parts and parts[0].isdigit():
                meminfo[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    except OSError:
        pass
    disk = shutil.disk_usage("/")
    io = read_disk_io()
    previous_io = state.get("disk_io") or {}
    io_delta = {
        key: max(0, value - int(previous_io.get(key, value))) for key, value in io.items()
    }
    state["disk_io"] = io
    try:
        load1, load5, load15 = os.getloadavg()
    except OSError:
        load1 = load5 = load15 = 0.0
    return {
        "hostname": socket.gethostname(),
        "cpu_count": os.cpu_count() or 0,
        "cpu_percent_since_previous": cpu_percent,
        "load_average": {"1m": round(load1, 3), "5m": round(load5, 3), "15m": round(load15, 3)},
        "memory": {
            "total_bytes": meminfo.get("MemTotal", 0),
            "available_bytes": meminfo.get("MemAvailable", 0),
            "swap_total_bytes": meminfo.get("SwapTotal", 0),
            "swap_free_bytes": meminfo.get("SwapFree", 0),
        },
        "website_process": read_service_process_metrics(service_name),
        "disk_root": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "available_bytes": disk.free,
            "used_percent": round(disk.used / disk.total * 100, 2) if disk.total else 0.0,
        },
        "disk_io_counters": io,
        "disk_io_delta": io_delta,
    }


def collect_metrics(
    *,
    node_id: str,
    access_patterns: list[str],
    active_paths: list[str],
    visitor_root: Path,
    output_dir: Path,
    service_name: str | None = None,
) -> dict[str, Any]:
    del active_paths  # Kept in the interface so collection and archive config can share one env file.
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "collector_state.json"
    state = load_json(state_path, {})
    if not isinstance(state, dict):
        state = {}
    daily = state.setdefault("daily", {})
    if not isinstance(daily, dict):
        daily = {}
        state["daily"] = daily
    paths = expand_patterns(access_patterns)
    parse_errors = read_incremental_access_logs(paths, state, daily)
    visitor_counts = collect_visitor_counts(visitor_root)
    for day, count in visitor_counts.items():
        daily.setdefault(day, empty_day())["unique_visitors"] = count
    for item in daily.values():
        item.setdefault("unique_visitors", 0)
    snapshot = {
        "schema_version": 1,
        "checked_at": utc_now(),
        "node_id": node_id,
        "access_log_files": len(paths),
        "access_parse_errors": parse_errors,
        "resources": resource_snapshot(state, service_name),
    }
    snapshots_path = output_dir / "snapshots.jsonl"
    with snapshots_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(snapshots_path, 0o600)
    atomic_write_json(output_dir / "daily.json", {"schema_version": 1, "node_id": node_id, "days": daily})
    atomic_write_json(state_path, state)
    atomic_write_json(output_dir / "latest.json", snapshot)
    return snapshot


def validate_private_credentials(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ObservabilityError(f"COS credentials file not found: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ObservabilityError(f"COS credentials file is too permissive: mode={mode:o}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservabilityError(f"cannot read COS credentials file: {exc}") from exc
    if not isinstance(value, dict) or not value.get("secret_id") or not value.get("secret_key"):
        raise ObservabilityError("COS credentials file has invalid fields")
    return {"secret_id": str(value["secret_id"]), "secret_key": str(value["secret_key"])}


def rclone_command(config: Path, credentials: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    if not config.is_file():
        raise ObservabilityError(f"rclone config not found: {config}")
    if shutil.which("rclone") is None:
        raise ObservabilityError("rclone is not installed")
    values = validate_private_credentials(credentials)
    env = os.environ.copy()
    env["RCLONE_S3_ACCESS_KEY_ID"] = values["secret_id"]
    env["RCLONE_S3_SECRET_ACCESS_KEY"] = values["secret_key"]
    result = subprocess.run(
        ["rclone", "--config", str(config), *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "rclone failed").strip()
        raise ObservabilityError(message[-1000:])
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def archive_logs(
    *,
    node_id: str,
    log_patterns: list[str],
    active_paths: list[str],
    state_dir: Path,
    threshold_bytes: int,
    rclone_config: Path | None,
    credentials_file: Path | None,
    remote: str,
    bucket: str,
    prefix: str,
) -> dict[str, Any]:
    files = expand_patterns(log_patterns)
    active = {str(path.resolve()) for path in expand_patterns(active_paths)}
    total_bytes = sum(path.stat().st_size for path in files)
    result: dict[str, Any] = {
        "checked_at": utc_now(),
        "node_id": node_id,
        "log_file_count": len(files),
        "total_bytes": total_bytes,
        "threshold_bytes": threshold_bytes,
        "archived": False,
    }
    if total_bytes <= threshold_bytes:
        return result
    candidates = [path for path in files if str(path) not in active]
    candidates.sort(key=lambda path: (path.stat().st_mtime_ns, str(path)))
    reclaim = total_bytes - threshold_bytes
    selected: list[Path] = []
    selected_bytes = 0
    for path in candidates:
        selected.append(path)
        selected_bytes += path.stat().st_size
        if selected_bytes >= reclaim:
            break
    if not selected or selected_bytes < reclaim:
        raise ObservabilityError(
            "log threshold exceeded but no safe rotated files cover the reclaim target",
            code="no_safe_rotated_files",
            total_bytes=total_bytes,
        )
    if rclone_config is None or credentials_file is None:
        raise ObservabilityError(
            "COS archive is not configured; refusing to delete logs",
            code="cos_not_configured",
            total_bytes=total_bytes,
        )

    state_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_name = f"{node_id}-nginx-logs-{timestamp}.tar.gz"
    temp_path = state_dir / f".{archive_name}.tmp"
    manifest: list[dict[str, Any]] = []
    try:
        for path in selected:
            stat_result = path.stat()
            manifest.append(
                {
                    "path": str(path),
                    "size": stat_result.st_size,
                    "mtime_ns": stat_result.st_mtime_ns,
                    "inode": stat_result.st_ino,
                    "sha256": file_sha256(path),
                }
            )
        with tarfile.open(temp_path, "w:gz") as archive:
            info = tarfile.TarInfo("manifest.json")
            manifest_bytes = json.dumps(
                {"schema_version": 1, "node_id": node_id, "created_at": utc_now(), "files": manifest},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            info.size = len(manifest_bytes)
            info.mode = 0o600
            import io

            archive.addfile(info, io.BytesIO(manifest_bytes))
            for path in selected:
                archive.add(path, arcname=path.as_posix().lstrip("/"), recursive=False)
        object_prefix = f"{prefix.strip('/')}/{node_id}/{datetime.now(timezone.utc):%Y/%m/%d}"
        object_path = f"{remote}:{bucket}/{object_prefix}/{archive_name}"
        rclone_command(rclone_config, credentials_file, ["copyto", str(temp_path), object_path, "--immutable"])
        listing = rclone_command(
            rclone_config,
            credentials_file,
            ["lsjson", object_path, "--files-only"],
        )
        try:
            remote_items = json.loads(listing.stdout or "[]")
            remote_size = int(remote_items[0]["Size"]) if remote_items else -1
        except (ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ObservabilityError(
                f"COS archive verification returned invalid metadata: {exc}",
                code="remote_metadata_invalid",
                total_bytes=total_bytes,
            ) from exc
        local_size = temp_path.stat().st_size
        if remote_size != local_size:
            raise ObservabilityError(
                f"COS archive size mismatch: local={local_size}, remote={remote_size}",
                code="remote_size_mismatch",
                total_bytes=total_bytes,
            )
        for item in manifest:
            path = Path(item["path"])
            current = path.stat()
            if (
                current.st_ino != item["inode"]
                or current.st_size != item["size"]
                or current.st_mtime_ns != item["mtime_ns"]
            ):
                raise ObservabilityError(
                    f"log changed during archive; refusing deletion: {path}",
                    code="source_changed",
                    total_bytes=total_bytes,
                )
        for item in manifest:
            Path(item["path"]).unlink()
        receipt = {
            "schema_version": 1,
            "archived_at": utc_now(),
            "node_id": node_id,
            "object_path": object_path,
            "archive_size": local_size,
            "files": manifest,
        }
        with (state_dir / "receipts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(state_dir / "receipts.jsonl", 0o600)
        result.update({"archived": True, "archive_size": local_size, "deleted_files": len(manifest), "object_path": object_path})
        return result
    finally:
        temp_path.unlink(missing_ok=True)


def env_list(name: str, default: str) -> list[str]:
    value = os.getenv(name, default).strip()
    return shlex.split(value) if value else []


def _alert_state_path(state_dir: Path) -> Path:
    return state_dir / "alert_state.json"


def _load_alert_state(state_dir: Path) -> dict[str, Any]:
    value = load_json(_alert_state_path(state_dir), {})
    return value if isinstance(value, dict) else {}


def _save_alert_state(state_dir: Path, value: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_alert_state_path(state_dir), value)


def _service_identity() -> tuple[int, int]:
    account = os.getenv("WEBSITE_ALERT_SERVICE_USER", "snh48-web").strip() or "snh48-web"
    try:
        entry = pwd.getpwnam(account)
    except KeyError as exc:
        raise ObservabilityError("website alert service account is missing", code="alert_persist_failed") from exc
    return entry.pw_uid, entry.pw_gid


def _atomic_create_service_file(path: Path, content: bytes) -> bool:
    uid, gid = _service_identity()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(path.parent, uid, gid)
    os.chmod(path.parent, 0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return True


def _atomic_replace_service_file(path: Path, content: bytes) -> None:
    uid, gid = _service_identity()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(path.parent, uid, gid)
    os.chmod(path.parent, 0o700)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def persist_observability_event(
    *,
    node_id: str,
    incident_id: str,
    state: str,
    reason: str,
    details: str,
    total_bytes: int,
    threshold_bytes: int,
) -> dict[str, Any]:
    """Persist a safe local event and queue it for the website's peer worker."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", node_id):
        raise ObservabilityError("invalid alert node id", code="alert_persist_failed")
    if state not in {"active", "resolved"}:
        raise ObservabilityError("invalid alert state", code="alert_persist_failed")
    transition = "RECOVERY" if state == "resolved" else "ALERT"
    digest = hashlib.sha256(f"{node_id}|nginx_log_archive|{incident_id}|{state}".encode("utf-8")).hexdigest()[:24].upper()
    event_id = f"OBS-{transition}-{digest}"
    created_at = utc_now()
    event = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "observability_recovery" if state == "resolved" else "observability_alert",
        "created_at": created_at,
        "origin_node": node_id,
        # The event is replicated by ID to the peer.  Derive its label from
        # the canonical node map so both copies remain byte-for-byte equal.
        "origin_label": DEFAULT_NODE_LABELS.get(node_id, node_id),
        "payload": {
            "alert_key": "nginx_log_archive",
            "incident_id": incident_id,
            "state": state,
            "severity": "info" if state == "resolved" else "error",
            "reason": str(reason).strip()[:300],
            "details": str(details).strip()[:1000],
            "total_bytes": max(0, int(total_bytes)),
            "threshold_bytes": max(0, int(threshold_bytes)),
            "checked_at": created_at,
        },
    }
    content = json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    inbox_root = Path(os.getenv("WEBSITE_ALERT_ACTION_INBOX_ROOT", DEFAULT_ACTION_INBOX_ROOT))
    event_path = inbox_root / "events" / f"{event_id}.json"
    created = _atomic_create_service_file(event_path, content)
    if not created and event_path.read_bytes() != content:
        raise ObservabilityError("observability event id collision", code="alert_persist_failed")
    outbox_root = Path(os.getenv("WEBSITE_ALERT_OUTBOX_ROOT", DEFAULT_SHARED_OUTBOX_ROOT))
    _atomic_replace_service_file(outbox_root / "inbox" / f"{event_id}.json", content)
    return event


def _emit_archive_alert_transition(
    *,
    state_dir: Path,
    node_id: str,
    state: str,
    reason: str,
    details: str,
    total_bytes: int,
    threshold_bytes: int,
) -> None:
    """Write one durable alert only when the archive state changes."""
    alert_key = "nginx_log_archive"
    state_dir.mkdir(parents=True, exist_ok=True)
    previous = _load_alert_state(state_dir).get(alert_key)
    fingerprint = reason if state == "active" else "resolved"
    if state == "resolved" and not (isinstance(previous, dict) and previous.get("state") == "active"):
        return
    if isinstance(previous, dict) and previous.get("state") == state and previous.get("fingerprint") == fingerprint:
        return
    incident_id = str((previous or {}).get("incident_id") or "") if isinstance(previous, dict) else ""
    if state == "active":
        incident_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{os.urandom(6).hex()}"
    if not incident_id:
        return
    try:
        persist_observability_event(
            node_id=node_id,
            incident_id=incident_id,
            state=state,
            reason=reason,
            details=details,
            total_bytes=total_bytes,
            threshold_bytes=threshold_bytes,
        )
        print("website_observability: alert queued for website peer replication", file=sys.stderr)
    except (ObservabilityError, OSError) as exc:  # Alerting must not change fail-closed deletion behavior.
        print(f"website_observability: unable to persist alert: {exc}", file=sys.stderr)
        return
    _save_alert_state(
        state_dir,
        {
            **_load_alert_state(state_dir),
            alert_key: {
                "state": state,
                "fingerprint": fingerprint,
                "incident_id": incident_id,
                "updated_at": utc_now(),
            },
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--node-id", default=os.getenv("WEBSITE_METRICS_NODE_ID", socket.gethostname()))
    collect.add_argument("--access-pattern", action="append", default=None)
    collect.add_argument("--active-path", action="append", default=None)
    collect.add_argument("--visitor-root", default=os.getenv("WEBSITE_METRICS_VISITOR_ROOT", "/home/snh48_web/website/data/interaction_logs"))
    collect.add_argument("--output-dir", default=os.getenv("WEBSITE_METRICS_OUTPUT_DIR", DEFAULT_METRICS_ROOT))
    collect.add_argument("--service-name", default=os.getenv("WEBSITE_METRICS_SERVICE_NAME"))
    collect.set_defaults(handler=command_collect)

    archive = subparsers.add_parser("archive-logs")
    archive.add_argument("--node-id", default=os.getenv("WEBSITE_LOG_ARCHIVE_NODE_ID", socket.gethostname()))
    archive.add_argument("--log-pattern", action="append", default=None)
    archive.add_argument("--active-path", action="append", default=None)
    archive.add_argument("--state-dir", default=os.getenv("WEBSITE_LOG_ARCHIVE_STATE_DIR", DEFAULT_ARCHIVE_ROOT))
    archive.add_argument("--threshold-bytes", type=int, default=int(os.getenv("WEBSITE_LOG_ARCHIVE_THRESHOLD_BYTES", DEFAULT_THRESHOLD_BYTES)))
    archive.add_argument("--rclone-config", default=os.getenv("COS_RCLONE_CONFIG", ""))
    archive.add_argument("--credentials-file", default=os.getenv("COS_CREDENTIALS_FILE", ""))
    archive.add_argument("--remote", default=os.getenv("COS_REMOTE", "cjy_archive"))
    archive.add_argument("--bucket", default=os.getenv("COS_BUCKET", "cjy-archive-1429902869"))
    archive.add_argument("--prefix", default=os.getenv("COS_PREFIX", "website-logs"))
    archive.set_defaults(handler=command_archive)
    return parser


def command_collect(args: argparse.Namespace) -> int:
    snapshot = collect_metrics(
        node_id=args.node_id,
        access_patterns=args.access_pattern or env_list("WEBSITE_METRICS_ACCESS_PATTERNS", "/var/log/nginx/snh48_access.log*"),
        active_paths=args.active_path or env_list("WEBSITE_METRICS_ACTIVE_PATHS", "/var/log/nginx/snh48_access.log"),
        visitor_root=Path(args.visitor_root),
        output_dir=Path(args.output_dir),
        service_name=args.service_name or DEFAULT_SERVICE_NAMES.get(args.node_id),
    )
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    return 0


def command_archive(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    threshold_bytes = max(1, args.threshold_bytes)
    try:
        result = archive_logs(
            node_id=args.node_id,
            log_patterns=args.log_pattern or env_list("WEBSITE_LOG_ARCHIVE_PATTERNS", "/var/log/nginx/*.log*"),
            active_paths=args.active_path or env_list("WEBSITE_LOG_ARCHIVE_ACTIVE_PATHS", "/var/log/nginx/*.log"),
            state_dir=state_dir,
            threshold_bytes=threshold_bytes,
            rclone_config=Path(args.rclone_config) if args.rclone_config else None,
            credentials_file=Path(args.credentials_file) if args.credentials_file else None,
            remote=args.remote,
            bucket=args.bucket,
            prefix=args.prefix,
        )
    except ObservabilityError as exc:
        _emit_archive_alert_transition(
            state_dir=state_dir,
            node_id=args.node_id,
            state="active",
            reason=exc.code,
            details=str(exc),
            total_bytes=exc.total_bytes,
            threshold_bytes=threshold_bytes,
        )
        raise
    _emit_archive_alert_transition(
        state_dir=state_dir,
        node_id=args.node_id,
        state="resolved",
        reason="archive_check_ok",
        details="日志归档检查恢复正常；未发生未备份删除。",
        total_bytes=int(result.get("total_bytes") or 0),
        threshold_bytes=threshold_bytes,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except (ObservabilityError, OSError, ValueError) as exc:
        print(f"website_observability: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

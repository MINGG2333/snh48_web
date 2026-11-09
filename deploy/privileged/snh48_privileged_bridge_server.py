#!/usr/bin/env python3
"""Root-side Unix socket broker for narrowly allowlisted fan-hub commands."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import signal
import socket
import socketserver
import stat
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any


MAX_MESSAGE_BYTES = 1024 * 1024
FRAME_HEADER = struct.Struct("!I")
DEFAULT_FAN_ROOT = Path("/home/snh48-fan-hub")
SERVICE_SETTINGS = {
    "flip": {
        "commands": frozenset({
            "send-sms", "security-answer", "verify-code", "job-status", "latest-job",
            "messenger-status", "messenger-probe", "messenger-history", "messenger-send",
        }),
        "script": Path("scripts/web/flip_account_admin.py"),
        "timeout": 40,
        "command_timeouts": {
            "messenger-send": 380,
            "messenger-history": 45,
            "messenger-probe": 45,
            "messenger-status": 45,
        },
    },
    "social": {
        "commands": frozenset({"status", "update", "set-primary"}),
        "script": Path("scripts/web/social_credentials_admin.py"),
        "timeout": 170,
    },
}

# POSIX ACL access xattr layout from linux/posix_acl_xattr.h.
ACL_XATTR = "system.posix_acl_access"
ACL_VERSION = 2
ACL_TAG_USER_OBJ = 0x01
ACL_TAG_USER = 0x02
ACL_TAG_MASK = 0x10
ACL_PERM_WRITE = 0x02
# The project maintenance ACL grants these accounts write access to source
# trees, including the bridge scripts executed as root. Root remains the only
# principal allowed to change file ownership or ACLs.
TRUSTED_WRITER_ACCOUNTS = ("codex-feishu", "cjy-sync")


class BridgeFailure(RuntimeError):
    """Internal bridge failure that must not expose subprocess details."""


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise BridgeFailure("incomplete request")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_frame(connection: socket.socket) -> bytes:
    (size,) = FRAME_HEADER.unpack(_recv_exact(connection, FRAME_HEADER.size))
    if size <= 0 or size > MAX_MESSAGE_BYTES:
        raise BridgeFailure("invalid request size")
    return _recv_exact(connection, size)


def send_frame(connection: socket.socket, payload: bytes) -> None:
    if not payload or len(payload) > MAX_MESSAGE_BYTES:
        raise BridgeFailure("invalid response size")
    connection.sendall(FRAME_HEADER.pack(len(payload)) + payload)


def _trusted_writer_uids() -> frozenset[int]:
    uids = {0}
    for account in TRUSTED_WRITER_ACCOUNTS:
        try:
            uids.add(pwd.getpwnam(account).pw_uid)
        except KeyError:
            continue
    return frozenset(uids)


def _acl_writers_are_trusted(raw_acl: bytes, trusted_uids: frozenset[int]) -> bool:
    """Allow write only for root and trusted maintainer accounts.

    The group bits reported by stat(2) mirror the ACL mask, so a filesystem
    with maintainer write ACLs looks group-writable even when the owning group
    entry itself is read-only. Inspect the ACL instead of trusting st_mode.
    """
    if len(raw_acl) < 4 or (len(raw_acl) - 4) % 8 != 0:
        return False
    if int.from_bytes(raw_acl[:4], "little") != ACL_VERSION:
        return False
    for offset in range(4, len(raw_acl), 8):
        tag, permissions, identifier = struct.unpack_from("<HHI", raw_acl, offset)
        if not permissions & ACL_PERM_WRITE:
            continue
        if tag == ACL_TAG_USER_OBJ or tag == ACL_TAG_MASK:
            continue
        if tag == ACL_TAG_USER and identifier in trusted_uids:
            continue
        return False
    return True


def _require_root_owned_readonly(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise BridgeFailure("bridge executable missing") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
        raise BridgeFailure("bridge executable is not trusted")
    if metadata.st_mode & 0o002:
        raise BridgeFailure("bridge executable is not trusted")
    if metadata.st_mode & 0o020:
        try:
            raw_acl = os.getxattr(resolved, ACL_XATTR)
        except OSError as exc:
            raise BridgeFailure("bridge executable is not trusted") from exc
        if not _acl_writers_are_trusted(raw_acl, _trusted_writer_uids()):
            raise BridgeFailure("bridge executable is not trusted")
    return resolved


class CommandBroker:
    def __init__(self, service: str, fan_root: Path) -> None:
        if service not in SERVICE_SETTINGS:
            raise ValueError("unsupported service")
        self.service = service
        self.settings = SERVICE_SETTINGS[service]
        self.fan_root = fan_root.resolve(strict=True)

    def run(self, request: dict[str, Any]) -> str:
        command = request.get("command")
        payload = request.get("payload")
        if command not in self.settings["commands"] or not isinstance(payload, dict):
            raise BridgeFailure("request not allowlisted")

        python = _require_root_owned_readonly(self.fan_root / "venv/bin/python3")
        script = _require_root_owned_readonly(self.fan_root / self.settings["script"])
        stdin_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(stdin_payload.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise BridgeFailure("payload too large")

        process = subprocess.Popen(
            [str(python), str(script), str(command)],
            cwd=self.fan_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        try:
            stdout, _ = process.communicate(
                stdin_payload,
                timeout=int(
                    self.settings.get("command_timeouts", {}).get(
                        command, self.settings["timeout"]
                    )
                ),
            )
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise BridgeFailure("bridge command timed out") from exc

        output = (stdout or "").strip()
        if not output or len(output.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise BridgeFailure("invalid bridge response")
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            raise BridgeFailure("invalid bridge response") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("ok"), bool):
            raise BridgeFailure("invalid bridge response")
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


class BridgeRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, BridgeSocketServer)
        command = "unknown"
        try:
            _pid, uid, _gid = struct.unpack(
                "3i",
                self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")),
            )
            if uid not in server.allowed_uids:
                raise BridgeFailure("peer not allowed")
            request = json.loads(receive_frame(self.request).decode("utf-8"))
            if not isinstance(request, dict):
                raise BridgeFailure("invalid request")
            candidate = str(request.get("command") or "")
            command = candidate if candidate in server.broker.settings["commands"] else "rejected"
            output = server.broker.run(request)
            response = json.dumps({"ok": True, "stdout": output}, separators=(",", ":")).encode("utf-8")
            send_frame(self.request, response)
        except (BridgeFailure, OSError, UnicodeDecodeError, json.JSONDecodeError):
            print(
                f"privileged bridge request failed: service={server.broker.service} command={command}",
                file=sys.stderr,
                flush=True,
            )


class BridgeSocketServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(
        self,
        socket_path: Path,
        broker: CommandBroker,
        allowed_uids: frozenset[int],
    ) -> None:
        self.broker = broker
        self.allowed_uids = allowed_uids
        super().__init__(str(socket_path), BridgeRequestHandler)
        os.chmod(socket_path, 0o660)


def _prepare_socket(path: Path) -> None:
    if not path.parent.is_dir():
        raise SystemExit(f"runtime directory does not exist: {path.parent}")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if metadata.st_uid != 0 or not stat.S_ISSOCK(metadata.st_mode):
        raise SystemExit(f"refusing to replace unexpected socket path: {path}")
    path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=tuple(SERVICE_SETTINGS))
    parser.add_argument("--fan-root", type=Path, default=DEFAULT_FAN_ROOT)
    parser.add_argument("--socket-path", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("the privileged bridge server must run as root")

    socket_path = args.socket_path or Path(
        f"/run/snh48-privileged-bridge-{args.service}/bridge.sock"
    )
    _prepare_socket(socket_path)
    web_uid = pwd.getpwnam("snh48-web").pw_uid
    broker = CommandBroker(args.service, args.fan_root)
    with BridgeSocketServer(socket_path, broker, frozenset({0, web_uid})) as server:
        print(f"privileged bridge ready: service={args.service}", flush=True)
        server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

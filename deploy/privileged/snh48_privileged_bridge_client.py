#!/usr/bin/env python3
"""Unprivileged client for the local fan-hub privileged bridge."""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
from pathlib import Path


MAX_MESSAGE_BYTES = 1024 * 1024
FRAME_HEADER = struct.Struct("!I")
COMMANDS = {
    "flip": frozenset({"send-sms", "security-answer", "verify-code", "job-status", "latest-job"}),
    "social": frozenset({"status", "update"}),
}
TIMEOUTS = {"flip": 45, "social": 175}


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise RuntimeError("incomplete bridge response")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_frame(connection: socket.socket) -> bytes:
    (size,) = FRAME_HEADER.unpack(_recv_exact(connection, FRAME_HEADER.size))
    if size <= 0 or size > MAX_MESSAGE_BYTES:
        raise RuntimeError("invalid bridge response")
    return _recv_exact(connection, size)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=tuple(COMMANDS))
    parser.add_argument("command")
    args = parser.parse_args()
    if args.command not in COMMANDS[args.service]:
        print("unsupported bridge command", file=sys.stderr)
        return 64

    raw_payload = sys.stdin.buffer.read(MAX_MESSAGE_BYTES + 1)
    if len(raw_payload) > MAX_MESSAGE_BYTES:
        print("bridge payload is too large", file=sys.stderr)
        return 65
    try:
        payload = json.loads(raw_payload or b"{}")
    except json.JSONDecodeError:
        print("bridge payload is invalid", file=sys.stderr)
        return 65
    if not isinstance(payload, dict):
        print("bridge payload must be an object", file=sys.stderr)
        return 65

    request = json.dumps(
        {"command": args.command, "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    runtime_root = Path(os.getenv("SNH48_PRIVILEGED_BRIDGE_SOCKET_ROOT", "/run"))
    socket_path = runtime_root / f"snh48-privileged-bridge-{args.service}" / "bridge.sock"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(TIMEOUTS[args.service])
            connection.connect(str(socket_path))
            connection.sendall(FRAME_HEADER.pack(len(request)) + request)
            response = json.loads(receive_frame(connection).decode("utf-8"))
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise RuntimeError("bridge rejected request")
        stdout = response.get("stdout")
        if not isinstance(stdout, str):
            raise RuntimeError("bridge response is invalid")
        parsed_stdout = json.loads(stdout)
        if not isinstance(parsed_stdout, dict):
            raise RuntimeError("bridge response is invalid")
    except (OSError, RuntimeError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        print("privileged bridge unavailable", file=sys.stderr)
        return 70

    sys.stdout.write(stdout + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

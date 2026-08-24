#!/usr/bin/env python3
"""Atomically set one secret in an env file without exposing its value."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile
from pathlib import Path


KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_ENV_BYTES = 1024 * 1024


def update_env_secret(path: Path, key: str, secret: str, *, create: bool = False) -> None:
    if not KEY_RE.fullmatch(key):
        raise ValueError("invalid environment key")
    if not secret or "\n" in secret or "\r" in secret or "\0" in secret:
        raise ValueError("secret must be non-empty and single-line")
    if path.is_symlink():
        raise ValueError("refusing to replace a symlink")

    owner_uid = os.geteuid()
    owner_gid = os.getegid()
    original = ""
    if path.exists():
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("target is not a regular file")
        if metadata.st_size > MAX_ENV_BYTES:
            raise ValueError("env file is unexpectedly large")
        owner_uid = metadata.st_uid
        owner_gid = metadata.st_gid
        original = path.read_text(encoding="utf-8")
    elif not create:
        raise FileNotFoundError(path)

    lines = original.splitlines()
    matches = [
        index
        for index, line in enumerate(lines)
        if line.startswith(f"{key}=")
    ]
    if len(matches) > 1:
        raise ValueError(f"duplicate environment key: {key}")
    replacement = f"{key}={secret}"
    if matches:
        lines[matches[0]] = replacement
    else:
        lines.append(replacement)
    payload = ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, owner_uid, owner_gid)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--create", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if sys.stdin.isatty():
        raise SystemExit("refusing to read a secret from an interactive terminal")
    secret = sys.stdin.read()
    if secret.endswith("\n"):
        secret = secret[:-1]
    update_env_secret(args.file, args.key, secret, create=args.create)
    print(f"updated {args.key} in {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Download and atomically install the monthly DB-IP City Lite MMDB."""
from __future__ import annotations

import argparse
import gzip
import grp
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "website" / "data" / "geoip" / "dbip-city-lite.mmdb"
MAX_COMPRESSED_BYTES = 180 * 1024 * 1024
MAX_DATABASE_BYTES = 300 * 1024 * 1024


def _month(value: str) -> str:
    if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", value):
        raise argparse.ArgumentTypeError("month must use YYYY-MM")
    return value


def _download(source_url: str, destination: Path) -> int:
    request = Request(source_url, headers={"User-Agent": "snh48-web-geoip-updater/1.0"})
    written = 0
    with urlopen(request, timeout=120) as response, destination.open("wb") as output:
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > MAX_COMPRESSED_BYTES:
            raise RuntimeError("compressed database exceeds size limit")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_COMPRESSED_BYTES:
                raise RuntimeError("compressed database exceeds size limit")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    return written


def _decompress(source: Path, destination: Path) -> int:
    written = 0
    with gzip.open(source, "rb") as compressed, destination.open("wb") as output:
        while True:
            chunk = compressed.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_DATABASE_BYTES:
                raise RuntimeError("decompressed database exceeds size limit")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    return written


def _validate(path: Path) -> tuple[str, int]:
    import maxminddb

    with maxminddb.open_database(str(path)) as reader:
        metadata = reader.metadata()
        database_type = str(metadata.database_type)
        if "City" not in database_type:
            raise RuntimeError(f"unexpected MMDB type: {database_type}")
        if not reader.get("120.229.72.69"):
            raise RuntimeError("MMDB validation lookup returned no record")
        return database_type, int(metadata.build_epoch)


def main() -> int:
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", type=_month, default=current_month)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--group", default="", help="optional group owner, for example snh48-web")
    parser.add_argument("--source-url", default="")
    args = parser.parse_args()

    source_url = args.source_url or (
        f"https://download.db-ip.com/free/dbip-city-lite-{args.month}.mmdb.gz"
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    group_gid = None
    if args.group:
        group_gid = grp.getgrnam(args.group).gr_gid
        parent_mode = stat.S_IMODE(output.parent.stat().st_mode)
        os.chown(output.parent, -1, group_gid)
        os.chmod(output.parent, parent_mode | stat.S_IRGRP | stat.S_IXGRP)

    with tempfile.TemporaryDirectory(prefix="geoip-update-", dir=output.parent) as temp_dir:
        compressed = Path(temp_dir) / "database.mmdb.gz"
        candidate = Path(temp_dir) / "database.mmdb"
        compressed_size = _download(source_url, compressed)
        database_size = _decompress(compressed, candidate)
        database_type, build_epoch = _validate(candidate)
        os.chmod(candidate, 0o640)
        if group_gid is not None:
            os.chown(candidate, -1, group_gid)
        os.replace(candidate, output)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    build_date = datetime.fromtimestamp(build_epoch, tz=timezone.utc).date().isoformat()
    print(
        f"installed {database_type} build={build_date} compressed={compressed_size} "
        f"database={database_size} path={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

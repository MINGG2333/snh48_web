"""Resolve live cover images with the official CDN as the primary source.

The web pages must not depend on local cover files first: the CDN copy keeps
the public site lightweight and lets the local ``live_covers/`` archive stay
purely as a fallback.  The fan-hub recorder continues to download covers; this
module only decides which URL the pages should try first.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from website import config as cfg

_TIMESTAMP_FIELDS = ("push_bj", "live_ctime_bj", "start_bj")
_TIMESTAMP_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


def cover_dirs() -> list[Path]:
    """Return candidate local cover directories, in serving order."""
    root = Path(getattr(cfg, "LIVE_RECORD_ROOT", cfg.LIVE_PUSH_REPLAY_ROOT))
    return [
        root / "陈嘉仪_161808449" / "covers",
        root / "陈嘉仪_161808449" / "live_covers",
        Path("/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers"),
    ]


def _local_cover_name(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("cover_local_path") or "").strip()
    if explicit:
        return Path(explicit).name
    for field in _TIMESTAMP_FIELDS:
        match = _TIMESTAMP_RE.match(str(row.get(field) or "").strip())
        if match:
            year, month, day, hour, minute, second = match.groups()
            return f"{year}{month}{day}_{hour}{minute}{second}.jpg"
    return ""


def local_cover_url(row: Mapping[str, Any]) -> str:
    """Return the local fallback URL, or an empty string when none exists.

    An explicit ``cover_local_path`` column is trusted because it is written by
    the matcher.  Timestamp-derived names are only used when the file is
    actually present, so a missing download never produces a 404 fallback.
    """
    explicit = str(row.get("cover_local_path") or "").strip()
    name = _local_cover_name(row)
    if not name:
        return ""
    if explicit:
        return f"/live-covers/{name}"
    for directory in cover_dirs():
        try:
            if (directory / name).is_file():
                return f"/live-covers/{name}"
        except OSError:
            continue
    return ""


def cover_urls(row: Mapping[str, Any]) -> tuple[str, str]:
    """Return ``(primary_url, fallback_url)`` with CDN priority."""
    cdn = str(row.get("live_cover_url") or "").strip()
    if cdn.startswith("//"):
        primary = f"https:{cdn}"
    elif cdn.startswith(("http://", "https://")):
        primary = cdn
    elif cdn:
        primary = f"https://source3.48.cn{cdn}"
    else:
        primary = ""

    fallback = local_cover_url(row)
    if not primary and fallback:
        return fallback, ""
    return primary, fallback

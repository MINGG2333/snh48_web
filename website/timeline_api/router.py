"""
FastAPI router that serves LIVEPUSH records from snh48-fan-hub messages.csv
for the Timeline page.
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from website import config as cfg

router = APIRouter(prefix="/api/timeline", tags=["时光轴"])

# Beijing timezone
BJT = timezone(timedelta(hours=8))

# ── Member config ─────────────────────────────────────────────────────────
MEMBER_NAME = "陈嘉仪"
MEMBER_ID = "161808449"
MEMBER_DIR = f"{MEMBER_NAME}_{MEMBER_ID}"


def _get_messages_csv_path() -> Optional[Path]:
    """Return the path to messages.csv for the target member, or None."""
    root = Path(cfg.ROOM_RECORD_ROOT)
    csv_path = root / MEMBER_DIR / "messages.csv"
    if csv_path.exists():
        return csv_path
    # Also try the server production path
    server_path = Path(f"/home/snh48-fan-hub/room_record/{MEMBER_DIR}/messages.csv")
    if server_path.exists():
        return server_path
    return None


def _get_live_covers_dir() -> Optional[Path]:
    """Return the live_covers directory path."""
    root = Path(cfg.ROOM_RECORD_ROOT)
    covers_dir = root / MEMBER_DIR / "live_covers"
    if covers_dir.exists():
        return covers_dir
    server_path = Path(f"/home/snh48-fan-hub/room_record/{MEMBER_DIR}/live_covers")
    if server_path.exists():
        return server_path
    return None


def parse_bj_time(bj_time_str: str) -> Optional[datetime]:
    """Parse Beijing time string like '2025-10-06 01:43:20'."""
    if not bj_time_str:
        return None
    try:
        return datetime.strptime(bj_time_str.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=BJT)
    except (ValueError, AttributeError):
        return None


def extract_live_info(text_content: str) -> dict:
    """Extract liveTitle and liveCover from LIVEPUSH text_content JSON."""
    result = {"title": "", "cover_path": ""}
    if not text_content:
        return result
    try:
        data = json.loads(text_content)
        push = data.get("livePushInfo", {})
        result["title"] = push.get("liveTitle", "")
        result["cover_path"] = push.get("liveCover", "")
    except (json.JSONDecodeError, AttributeError):
        pass
    return result


def read_live_pushes(limit: int = 500) -> List[Dict[str, Any]]:
    """Read LIVEPUSH rows from messages.csv, return list of event dicts."""
    csv_path = _get_messages_csv_path()
    if not csv_path:
        return []

    covers_dir = _get_live_covers_dir()
    records = []

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("msg_type", "").strip() != "LIVEPUSH":
                    continue
                bj_time_str = row.get("bj_time", "").strip()
                dt = parse_bj_time(bj_time_str)
                if not dt:
                    continue

                live_info = extract_live_info(row.get("text_content", ""))
                media_path = row.get("media_path", "").strip()

                # Build cover URL: try local file first, then CDN
                cover_url = ""
                file_name = ""
                if media_path:
                    # media_path looks like "live_covers/20251006_014320.jpg"
                    file_name = Path(media_path).name
                    if covers_dir:
                        local_file = covers_dir / file_name
                        if local_file.exists():
                            cover_url = f"/api/timeline/cover/{MEMBER_NAME}_{MEMBER_ID}/{file_name}"

                record = {
                    "id": f"live_{dt.strftime('%Y%m%d_%H%M%S')}",
                    "date": dt.strftime("%Y-%m-%d"),
                    "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "title": live_info["title"] or f"直播 {dt.strftime('%m/%d %H:%M')}",
                    "type": "live",
                    "typeLabel": "直播",
                    "source": "room",
                    "description": f"📅 {dt.strftime('%Y-%m-%d %H:%M')}\n\n{live_info['title'] or '一场直播'}",
                    "cover_url": cover_url,
                    "icon": "fa-video",
                }
                records.append(record)

                if len(records) >= limit:
                    break
    except (IOError, csv.Error) as e:
        print(f"[timeline_api] Error reading CSV: {e}")
        return []

    return records


def group_live_by_date(records: List[Dict]) -> Dict[str, List[Dict]]:
    """Group live records by date string."""
    groups: Dict[str, List[Dict]] = {}
    for rec in records:
        d = rec["date"]
        groups.setdefault(d, []).append(rec)
    return groups


# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/live-pushes")
def get_live_pushes(
    limit: int = Query(500, ge=1, le=2000),
):
    """Return LIVEPUSH records as timeline-ready event list."""
    records = read_live_pushes(limit=limit)
    return {
        "success": True,
        "data": records,
        "total": len(records),
        "member": MEMBER_NAME,
    }


@router.get("/live-pushes/grouped")
def get_live_pushes_grouped(
    limit: int = Query(500, ge=1, le=2000),
):
    """Return LIVEPUSH records grouped by date (for same-day multi-card)."""
    records = read_live_pushes(limit=limit)
    groups = group_live_by_date(records)
    return {
        "success": True,
        "data": groups,
        "total": len(records),
        "member": MEMBER_NAME,
    }


@router.get("/cover/{member_dir}/{filename}")
def serve_live_cover(member_dir: str, filename: str):
    """Serve a live cover image from the local filesystem."""
    from fastapi.responses import FileResponse

    # Try local dev path
    local_path = Path(cfg.ROOM_RECORD_ROOT) / member_dir / "live_covers" / filename
    if local_path.exists():
        return FileResponse(str(local_path), media_type="image/jpeg")

    # Try server path
    server_path = Path(f"/home/snh48-fan-hub/room_record/{member_dir}/live_covers/{filename}")
    if server_path.exists():
        return FileResponse(str(server_path), media_type="image/jpeg")

    raise HTTPException(status_code=404, detail="Cover not found")

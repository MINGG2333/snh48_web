"""
FastAPI router that serves live push + replay data from
snh48-fan-hub live_push_replays/summary.csv for the Timeline page.

Summary CSV columns:
  key, member_name, member_id, live_id,
  push_time, push_bj, title, live_type,
  live_cover_url, cover_local_path,
  replay_status, video_status, danmu_status, last_checked_bj,
  play_url, danmu_url, video_local_path, danmu_local_path
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from website import config as cfg

router = APIRouter(prefix="/api/timeline", tags=["时光轴"])

BJT = timezone(timedelta(hours=8))

MEMBER_NAME = "陈嘉仪"
MEMBER_ID = "161808449"
MEMBER_DIR = f"{MEMBER_NAME}_{MEMBER_ID}"


def _get_summary_csv_path() -> Optional[Path]:
    """Locate summary.csv for the target member."""
    candidates = [
        Path(cfg.LIVE_PUSH_REPLAY_ROOT) / MEMBER_DIR / "summary.csv",
        Path("/home/snh48-fan-hub/live_push_replays") / MEMBER_DIR / "summary.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def parse_bj_time(bj_str: str) -> Optional[datetime]:
    """Parse '2025-10-06 01:43:20' → datetime (BJT)."""
    if not bj_str:
        return None
    try:
        return datetime.strptime(bj_str.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=BJT)
    except (ValueError, AttributeError):
        return None


def read_live_pushes(limit: int = 500) -> List[Dict[str, Any]]:
    """Read summary.csv, return list of timeline-ready event dicts."""
    csv_path = _get_summary_csv_path()
    if not csv_path:
        return []

    records = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                push_bj = (row.get("push_bj") or "").strip()
                dt = parse_bj_time(push_bj)
                if not dt:
                    continue

                # Cover: use local if available, else CDN
                cover_url = ""
                cover_local = (row.get("cover_local_path") or "").strip()
                if cover_local:
                    cover_url = f"/live-covers/{Path(cover_local).name}"
                else:
                    cdn = (row.get("live_cover_url") or "").strip()
                    if cdn:
                        cover_url = f"https://source3.48.cn{cdn}"

                # Replay video URL (may be empty if not available)
                replay_url = ""
                play_url = (row.get("play_url") or "").strip()
                video_status = (row.get("video_status") or "").strip()
                if play_url and video_status in ("available", "downloaded"):
                    replay_url = play_url

                title = (row.get("title") or "").strip() or f"直播 {dt.strftime('%m/%d %H:%M')}"

                live_id = (row.get("live_id") or "").strip()
                record_id = f"live_{live_id}" if live_id else f"live_{dt.strftime('%Y%m%d_%H%M%S')}"

                desc = f"📅 {dt.strftime('%Y-%m-%d %H:%M')}"
                if title:
                    desc += f"\n\n{title}"
                if replay_url:
                    desc += f"\n\n🎬 有回放视频"

                records.append({
                    "id": record_id,
                    "date": dt.strftime("%Y-%m-%d"),
                    "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "title": title,
                    "type": "live",
                    "typeLabel": "直播",
                    "source": "room",
                    "description": desc,
                    "cover_url": cover_url,
                    "replay_url": replay_url,
                    "has_replay": bool(replay_url),
                    "icon": "fa-video",
                })

                if len(records) >= limit:
                    break
    except (IOError, csv.Error) as e:
        print(f"[timeline_api] Error reading summary CSV: {e}")
        return []

    return records


def group_live_by_date(records: List[Dict]) -> Dict[str, List[Dict]]:
    groups: Dict[str, List[Dict]] = {}
    for rec in records:
        groups.setdefault(rec["date"], []).append(rec)
    return groups


# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/live-pushes")
def get_live_pushes(limit: int = Query(500, ge=1, le=2000)):
    """Return live+replay records as timeline-ready event list."""
    records = read_live_pushes(limit=limit)
    return {
        "success": True,
        "data": records,
        "total": len(records),
        "member": MEMBER_NAME,
    }


@router.get("/live-pushes/grouped")
def get_live_pushes_grouped(limit: int = Query(500, ge=1, le=2000)):
    """Return records grouped by date."""
    records = read_live_pushes(limit=limit)
    groups = group_live_by_date(records)
    return {
        "success": True,
        "data": groups,
        "total": len(records),
        "member": MEMBER_NAME,
    }




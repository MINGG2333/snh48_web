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
from urllib.request import Request, urlopen
import re

from fastapi import APIRouter, Query

from website import config as cfg

router = APIRouter(prefix="/api/timeline", tags=["时光轴"])

BJT = timezone(timedelta(hours=8))

MEMBER_NAME = "陈嘉仪"
MEMBER_ID = "161808449"
MEMBER_DIR = f"{MEMBER_NAME}_{MEMBER_ID}"

# ── 图片代理 ────────────────────────────────────────────────────────────
# 新浪微博图片有 Referer 防盗链，通过代理服务器加 Referer 头绕过
# Nginx 反向代理：/image-proxy/ → http://10.0.0.6:8899/
# 见 deploy/nginx.conf 中的配置
IMAGE_PROXY_INTERNAL_PREFIX = "/image-proxy"


def sinaimg_to_proxy(url: str) -> str:
    """将图片 URL 转为内部代理路径（sinaimg）或直接升级为 HTTPS（hdslb）"""
    if not url:
        return url
    try:
        # B站图片: http://i0.hdslb.com/... → https://i0.hdslb.com/...
        if "hdslb.com" in url:
            return url.replace("http://", "https://")
        # 新浪微博图片: https://wx1.sinaimg.cn/large/xxx → /image-proxy/large/xxx
        if ".sinaimg.cn" in url:
            path = url.split(".cn")[-1]
            return f"{IMAGE_PROXY_INTERNAL_PREFIX}{path}"
        return url
    except Exception:
        return url


def parse_multi_urls(val: str) -> List[str]:
    """解析分号分隔的多个 URL"""
    if not val:
        return []
    return [u.strip() for u in val.split(";") if u.strip()]


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


def _find_summary_row(live_id: str) -> Optional[Dict[str, Any]]:
    csv_path = _get_summary_csv_path()
    if not csv_path or not live_id:
        return None

    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row.get("live_id") or "").strip() == live_id.strip():
                    return row
    except (IOError, csv.Error):
        return None

    return None


def _resolve_danmu_file_path(path_str: str) -> Optional[Path]:
    if not path_str:
        return None
    path = Path(path_str.strip())
    if path.is_absolute() and path.exists():
        return path

    candidate = Path(cfg.LIVE_PUSH_REPLAY_ROOT) / MEMBER_DIR / path
    if candidate.exists():
        return candidate

    candidate = Path(cfg.LIVE_PUSH_REPLAY_ROOT) / path
    if candidate.exists():
        return candidate

    return None


def _read_text_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None


def _read_text_url(url: str) -> Optional[str]:
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:
            raw = response.read()
            return raw.decode("utf-8-sig", errors="ignore")
    except Exception:
        return None


def parse_pocket_danmu(file_content: str) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    time_regex = re.compile(r"\[(\d+):(\d+):(\d+)\.(\d+)\]")

    for line in file_content.splitlines():
        if not line.strip():
            continue
        match = time_regex.search(line)
        if not match:
            continue

        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = int(match.group(4))
        total_seconds = hours * 3600 + minutes * 60 + seconds + (milliseconds / 1000.0)

        content_part = line[match.end():].strip()
        nickname = "弹幕"
        text = content_part

        if '\t' in content_part:
            parts = content_part.split('\t')
            if len(parts) >= 2:
                nickname = parts[0].strip() or nickname
                text = ''.join(parts[1:]).strip() or text
        else:
            spaced_match = re.match(r"^(.+?)\s{2,}(.*)$", content_part)
            if spaced_match:
                nickname = spaced_match.group(1).strip() or nickname
                text = spaced_match.group(2).strip() or text
            else:
                fallback = re.split(r"\s+", content_part, maxsplit=1)
                if len(fallback) >= 2:
                    nickname = fallback[0].strip() or nickname
                    text = fallback[1].strip() or text

        result.append({
            "name": nickname or "弹幕",
            "text": text,
            "time": total_seconds,
            "color": "#ffffff",
            "border": False,
            "mode": 0,
        })

    return result


def _get_danmu_text(row: Dict[str, Any]) -> Optional[str]:
    danmu_local_path = (row.get("danmu_local_path") or "").strip()
    if danmu_local_path:
        file_path = _resolve_danmu_file_path(danmu_local_path)
        if file_path:
            content = _read_text_file(file_path)
            if content:
                return content

    danmu_url = (row.get("danmu_url") or "").strip()
    if danmu_url:
        return _read_text_url(danmu_url)

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

                const_danmu_local = (row.get("danmu_local_path") or "").strip()
                const_danmu_url = (row.get("danmu_url") or "").strip()
                has_danmu = bool(const_danmu_local or const_danmu_url)
                danmu_status = (row.get("danmu_status") or "").strip() or ("已生成" if has_danmu else "暂无弹幕")

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
                    "has_danmu": has_danmu,
                    "danmu_status": danmu_status,
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


@router.get("/danmu")
def get_live_danmu(live_id: str = Query(..., min_length=1)):
    """Return danmaku items for the requested live replay."""
    row = _find_summary_row(live_id)
    if not row:
        return {
            "success": False,
            "message": "未找到对应的直播 ID 或 summary.csv。",
            "data": [],
            "total": 0,
        }

    danmu_text = _get_danmu_text(row)
    if not danmu_text:
        return {
            "success": True,
            "message": "未找到弹幕文件或弹幕文件为空。",
            "data": [],
            "total": 0,
        }

    danmu_items = parse_pocket_danmu(danmu_text)
    return {
        "success": True,
        "data": danmu_items,
        "total": len(danmu_items),
    }


# ── Schedule (行程表) ─────────────────────────────────────────────────────

TYPE_LABEL_MAP = {
    "公演": "公演",
    "外务": "外务",
    "见面会": "见面会",
    "里程碑": "里程碑",
    "日常": "日常",
    "其他": "其他",
}


def read_schedule() -> List[Dict[str, Any]]:
    """Read schedule.csv, return list of timeline-ready event dicts."""
    csv_path_str = cfg.SCHEDULE_CSV_PATH
    if not csv_path_str:
        return []

    csv_path = Path(csv_path_str)
    # Also try the server path
    if not csv_path.exists():
        csv_path = Path("/home/snh48-fan-hub/schedule_record/schedule.csv")
    if not csv_path.exists():
        return []

    records = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_str = (row.get("date") or "").strip()
                if not date_str:
                    continue

                # Skip deleted entries
                is_deleted = (row.get("delete") or "").strip()
                if is_deleted:
                    continue

                name = (row.get("name") or "").strip()
                event_type = (row.get("type") or "其他").strip()
                time_str = (row.get("time") or "").strip()
                type_label = TYPE_LABEL_MAP.get(event_type, event_type)

                # event_type (行程/里程碑/日常)
                row_event_type = (row.get("event_type") or "").strip()

                # Optional enhanced fields from CSV
                location = (row.get("location") or "").strip()
                cover_url_src = (row.get("cover_url") or "").strip()
                source_url = (row.get("source_url") or "").strip()
                csv_desc = (row.get("description") or "").strip()
                event_link = (row.get("event_link") or "").strip()
                remark = (row.get("remark") or "").strip()
                # event_images has top priority: always overrides image_urls, and its first image becomes cover_url
                event_images = [sinaimg_to_proxy(u) for u in parse_multi_urls(row.get("event_images"))]
                if event_images:
                    image_urls = event_images
                    cover_url = event_images[0]
                else:
                    image_urls = [sinaimg_to_proxy(u) for u in parse_multi_urls(row.get("image_urls"))]
                    cover_url = sinaimg_to_proxy(cover_url_src)
                bilibili_urls = parse_multi_urls(row.get("snh48_bilibili_urls"))
                chenjiayi_weibo_urls = parse_multi_urls(row.get("chenjiayi_weibo_urls"))
                snh48_weibo_urls = parse_multi_urls(row.get("snh48_weibo_urls"))

                # Build description: use CSV description if provided, else auto-generate
                if csv_desc:
                    desc_parts = [csv_desc]
                else:
                    desc_parts = [f"📅 {date_str}"]
                    if time_str:
                        desc_parts.append(f"🕐 {time_str}")
                    if location:
                        desc_parts.append(f"📍 {location}")
                    desc_parts.append(f"\n\n{name}")

                title = name

                # Icon: use CSV column if provided, otherwise fallback by type
                icon = (row.get("icon") or "").strip()
                if not icon:
                    icon = {
                        "公演": "fa-music",
                        "外务": "fa-plane",
                        "见面会": "fa-handshake",
                        "里程碑": "fa-star",
                        "日常": "fa-heart",
                    }.get(event_type, "fa-calendar-check")

                records.append({
                    "id": f"sched_{date_str}_{name}_{event_type}",
                    "date": date_str,
                    "datetime": f"{date_str} {time_str}" if time_str else f"{date_str} 00:00:00",
                    "title": title,
                    "type": event_type,
                    "typeLabel": type_label,
                    "eventType": row_event_type,
                    "source": "assistant",
                    "description": "\n".join(desc_parts),
                    "cover_url": cover_url,
                    "icon": icon,
                    "location": location,
                    "source_url": source_url,
                    "image_urls": image_urls,
                    "event_link": event_link,
                    "bilibili_urls": bilibili_urls,
                })
    except (IOError, csv.Error) as e:
        print(f"[timeline_api] Error reading schedule CSV: {e}")
        return []

    # Sort by date
    records.sort(key=lambda r: r["date"])
    return records


@router.get("/schedule")
def get_schedule():
    """Return schedule records as timeline-ready event list."""
    records = read_schedule()
    return {
        "success": True,
        "data": records,
        "total": len(records),
        "member": MEMBER_NAME,
    }
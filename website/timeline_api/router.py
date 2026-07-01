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
import hashlib
import ipaddress
import socket
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit
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


def _danmu_url_cache_dir() -> Path:
    if cfg.DANMU_REMOTE_CACHE_DIR:
        return Path(cfg.DANMU_REMOTE_CACHE_DIR)
    return Path(cfg.LIVE_PUSH_REPLAY_ROOT) / MEMBER_DIR / ".danmu_url_cache"


def _danmu_url_cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return _danmu_url_cache_dir() / f"{digest}.txt"


def _read_danmu_url_cache(url: str) -> Optional[str]:
    cache_path = _danmu_url_cache_path(url)
    if not cache_path.exists():
        return None
    return _read_text_file(cache_path)


def _write_danmu_url_cache(url: str, content: str) -> None:
    if not content:
        return
    cache_path = _danmu_url_cache_path(url)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        print(f"[timeline_api] Failed to write danmu URL cache: {exc}")


def _host_matches_allowed(host: str, allowed: Tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    for item in allowed:
        item = item.lower().rstrip(".")
        if not item:
            continue
        if item.startswith(".") and host.endswith(item):
            return True
        if host == item or host.endswith(f".{item}"):
            return True
    return False


def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_global


def _validate_remote_danmu_url(url: str) -> Tuple[bool, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        return False, "unsupported scheme"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "missing host"
    if host in ("localhost",) or host.endswith(".localhost"):
        return False, "localhost is not allowed"

    try:
        port = parsed.port
    except ValueError:
        return False, "invalid port"
    if port is not None and port not in (80, 443):
        return False, "non-standard port is not allowed"

    allowed_hosts = cfg.DANMU_REMOTE_ALLOWED_HOSTS
    if allowed_hosts and not _host_matches_allowed(host, allowed_hosts):
        message = f"host {host} is outside DANMU_REMOTE_ALLOWED_HOSTS"
        if cfg.DANMU_REMOTE_ENFORCE_HOST_ALLOWLIST:
            return False, message
        print(f"[timeline_api] Danmu URL allowlist warning: {message}")

    try:
        addr_infos = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return False, f"DNS resolution failed: {exc}"

    for addr_info in addr_infos:
        address = addr_info[4][0]
        if not _is_public_ip(address):
            return False, f"non-public resolved address is not allowed: {address}"

    return True, ""


def _read_text_url(url: str) -> Optional[str]:
    allowed, reason = _validate_remote_danmu_url(url)
    if not allowed:
        print(f"[timeline_api] Blocked remote danmu URL: {reason}")
        return None

    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=cfg.DANMU_REMOTE_TIMEOUT_SECONDS) as response:
            chunks = []
            total = 0
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > cfg.DANMU_REMOTE_MAX_BYTES:
                    print(f"[timeline_api] Remote danmu response too large: {total} bytes")
                    return None
                chunks.append(chunk)
            raw = b"".join(chunks)
            return raw.decode("utf-8-sig", errors="ignore")
    except Exception as exc:
        print(f"[timeline_api] Failed to read remote danmu URL: {exc}")
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
        cached_content = _read_danmu_url_cache(danmu_url)
        if cached_content:
            return cached_content
        remote_content = _read_text_url(danmu_url)
        if remote_content:
            _write_danmu_url_cache(danmu_url, remote_content)
            return remote_content

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


def _find_schedule_csv() -> Optional[Path]:
    """Locate the primary event CSV, falling back to schedule.csv compatibility paths."""
    candidates = [
        cfg.EVENTS_CSV_PATH,
        cfg.SCHEDULE_CSV_PATH,
        "/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv",
        "/home/snh48-fan-hub/schedule_record/schedule.csv",
    ]
    seen = set()
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            return path
    return None


def read_schedule() -> List[Dict[str, Any]]:
    """Read the Chen Jiayi event CSV, return timeline-ready event dicts."""
    csv_path = _find_schedule_csv()
    if not csv_path:
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
                video_urls = parse_multi_urls(row.get("video_urls"))

                # Images: event_images shown first, then image_urls follows
                event_images = [sinaimg_to_proxy(u) for u in parse_multi_urls(row.get("event_images"))]
                csv_image_urls = [sinaimg_to_proxy(u) for u in parse_multi_urls(row.get("image_urls"))]
                all_images = event_images + csv_image_urls

                # Cover URL priority: manual cover_url → event_images[0] → image_urls[0]
                cover_url = sinaimg_to_proxy(cover_url_src)
                if not cover_url and event_images:
                    cover_url = event_images[0]
                if not cover_url and csv_image_urls:
                    cover_url = csv_image_urls[0]
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

                # Safe ID: sanitize name for HTML attribute use
                safe_id_name = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name)
                records.append({
                    "id": f"sched_{date_str}_{safe_id_name}_{event_type}",
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
                    "image_urls": all_images,
                    "event_link": event_link,
                    "video_urls": video_urls,
                    "bilibili_urls": bilibili_urls,
                    "snh48_weibo_urls": snh48_weibo_urls,
                    "chenjiayi_weibo_urls": chenjiayi_weibo_urls,
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


# ── Manual Events ────────────────────────────────────────────────────────
# Previously hardcoded in timeline.js, then hardcoded in this file.
# Now loaded from CSV so events can be updated without restarting the server.
# CSV columns: id, date, title, type, typeLabel, description, image, icon, link, images


def _find_manual_csv() -> Optional[Path]:
    """Locate manual_events.csv using config path (no hardcoded absolute paths)."""
    csv_path = Path(cfg.MANUAL_EVENTS_CSV_PATH)
    if csv_path.exists():
        return csv_path
    return None


def read_manual_events() -> List[Dict[str, Any]]:
    """Read manual_events.csv, return list of timeline-ready event dicts."""
    csv_path = _find_manual_csv()
    if not csv_path:
        return []

    records = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ev_id = (row.get("id") or "").strip()
                date_str = (row.get("date") or "").strip()
                if not ev_id or not date_str:
                    continue

                title = (row.get("title") or "").strip()
                ev_type = (row.get("type") or "event").strip()
                type_label = (row.get("typeLabel") or ev_type).strip()
                description = (row.get("description") or "").strip()
                image = (row.get("image") or "").strip() or None
                icon = (row.get("icon") or "fa-calendar").strip()
                link = (row.get("link") or "").strip() or None

                # Images: semicolon-separated URLs
                images_raw = (row.get("images") or "").strip()
                images = [u.strip() for u in images_raw.split(";") if u.strip()] if images_raw else []

                records.append({
                    "id": ev_id,
                    "source": "manual",
                    "date": date_str,
                    "title": title,
                    "type": ev_type,
                    "typeLabel": type_label,
                    "description": description,
                    "image": image,
                    "icon": icon,
                    "link": link,
                    "images": images,
                })
    except (IOError, csv.Error) as e:
        print(f"[timeline_api] Error reading manual events CSV: {e}")
        return []

    return records


@router.get("/manual-events")
def get_manual_events():
    """Return manually curated timeline events (loaded from CSV, no restart needed)."""
    records = read_manual_events()
    return {
        "success": True,
        "data": records,
        "total": len(records),
    }

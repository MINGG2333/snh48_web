"""
Room messages API router.

Exposes a password-protected, cursor-based view over the room_monitor
messages.csv dataset. The CSV is cached in memory and reloaded when the file
mtime changes.
"""
from __future__ import annotations

import csv
import hmac
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from website import config as cfg
from website.rate_limiter import check_admin_login_limit, get_client_ip

router = APIRouter(prefix="/api/room-messages", tags=["房间消息页"])

VALID_FAMILIES = {"all", "text", "reply", "gift", "gift_reply", "media", "flipcard", "live", "share", "event"}
VALID_MEDIA_FILTERS = {"all", "with", "without"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TYPE_LABELS = {
    "TEXT": "文本",
    "REPLY": "文字回复",
    "GIFT_TEXT": "礼物",
    "GIFTREPLY": "回礼物",
    "AUDIO_GIFT_REPLY": "语音回礼物",
    "IMAGE": "图片",
    "VIDEO": "视频",
    "AUDIO": "语音",
    "AUDIO_REPLY": "语音回复",
    "EXPRESSIMAGE": "表情包",
    "LIVEPUSH": "直播推送",
    "FLIPCARD": "文字翻牌",
    "FLIPCARD_AUDIO": "语音翻牌",
    "FLIPCARD_VIDEO": "视频翻牌",
    "SHARE_POSTS": "动态分享",
    "RED_PACKET_2026": "红包",
}

TYPE_FAMILIES = {
    "TEXT": "text",
    "REPLY": "reply",
    "AUDIO_REPLY": "reply",
    "GIFT_TEXT": "gift",
    "GIFTREPLY": "gift_reply",
    "AUDIO_GIFT_REPLY": "gift_reply",
    "IMAGE": "media",
    "VIDEO": "media",
    "AUDIO": "media",
    "EXPRESSIMAGE": "media",
    "FLIPCARD": "flipcard",
    "FLIPCARD_AUDIO": "flipcard",
    "FLIPCARD_VIDEO": "flipcard",
    "LIVEPUSH": "live",
    "SHARE_POSTS": "share",
    "RED_PACKET_2026": "event",
}

_cache_lock = threading.Lock()
_cache_mtime_ns = -1
_cache_rows: list[dict[str, Any]] = []
_cache_summary: dict[str, Any] = {}


async def verify_room_messages_password(
    request: Request,
    x_room_messages_password: str = Header(None, alias="X-Room-Messages-Password"),
):
    """Verify room messages page password."""
    expected = cfg.ROOM_MESSAGES_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="房间消息页未启用",
        )
    if not x_room_messages_password:
        check_room_messages_login_limit(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要密码",
        )
    if not hmac.compare_digest(expected, x_room_messages_password):
        check_room_messages_login_limit(request)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="密码错误",
        )
    return True


def check_room_messages_login_limit(request: Request) -> None:
    check_admin_login_limit(get_client_ip(request), "房间消息页密码尝试过于频繁，请稍后再试")


@router.get("/data")
def get_room_messages_data(
    response: Response,
    limit: int = Query(100, ge=20, le=500),
    before_index: int | None = Query(None, ge=0),
    target_id: str = Query(""),
    msg_type: str = Query("all"),
    family: str = Query("all"),
    sender: str = Query(""),
    keyword: str = Query(""),
    has_media: str = Query("all"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    _=Depends(verify_room_messages_password),
):
    """Return one chat-style chunk, newest chunk by default, older chunks by cursor."""
    response.headers["Cache-Control"] = "no-store"

    msg_type = msg_type.strip().upper()
    if msg_type == "":
        msg_type = "ALL"
    families = _parse_families(family)
    has_media = has_media.strip().lower()

    if has_media not in VALID_MEDIA_FILTERS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的媒体筛选")
    _validate_date("date_from", date_from)
    _validate_date("date_to", date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="日期范围无效")

    rows, summary = _load_dataset()
    sender = sender.strip()
    keyword = keyword.strip()
    date_from = date_from.strip()
    date_to = date_to.strip()
    target_id = target_id.strip()

    if _is_unfiltered(
        msg_type=msg_type,
        families=families,
        sender=sender,
        keyword=keyword,
        has_media=has_media,
        date_from=date_from,
        date_to=date_to,
    ):
        total = len(rows)
        target_index = _find_row_index(rows, target_id) if target_id else None
        if target_id and target_index is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标消息不在当前筛选结果中")
        end = _chunk_end(total, before_index, target_index)
        start = max(0, end - limit)
        items = [_public_row(row) for row in rows[start:end]]
    else:
        filtered = _filter_rows(
            rows,
            msg_type=msg_type,
            families=families,
            sender=sender,
            keyword=keyword,
            has_media=has_media,
            date_from=date_from,
            date_to=date_to,
        )

        total = len(filtered)
        target_index = _find_row_index(filtered, target_id) if target_id else None
        if target_id and target_index is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标消息不在当前筛选结果中")
        end = _chunk_end(total, before_index, target_index)
        start = max(0, end - limit)
        items = [_public_row(row) for row in filtered[start:end]]

    return {
        "items": items,
        "limit": limit,
        "total": total,
        "start_index": start,
        "end_index": end,
        "next_before_index": start,
        "has_more_older": start > 0,
        "target_id": target_id,
        "target_found": bool(target_id),
        "summary": summary,
        "type_counts": summary.get("type_counts", []),
        "family_counts": summary.get("family_counts", []),
        "refresh_interval_seconds": cfg.ROOM_MESSAGES_REFRESH_INTERVAL_SECONDS,
    }


@router.get("/summary")
def get_room_messages_summary(
    response: Response,
    _=Depends(verify_room_messages_password),
):
    """Return room message summary and type counts."""
    response.headers["Cache-Control"] = "no-store"
    _, summary = _load_dataset()
    return {
        "summary": summary,
        "type_counts": summary.get("type_counts", []),
        "family_counts": summary.get("family_counts", []),
        "refresh_interval_seconds": cfg.ROOM_MESSAGES_REFRESH_INTERVAL_SECONDS,
    }


def _data_path() -> Path:
    return Path(cfg.ROOM_MESSAGES_CSV_PATH)


def _load_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global _cache_mtime_ns, _cache_rows, _cache_summary

    path = _data_path()
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="房间消息数据未生成")

    stat = path.stat()
    if _cache_mtime_ns == stat.st_mtime_ns:
        return _cache_rows, _cache_summary

    with _cache_lock:
        stat = path.stat()
        if _cache_mtime_ns == stat.st_mtime_ns:
            return _cache_rows, _cache_summary

        rows: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    normalised = _normalise_row(row)
                    normalised["_row_index"] = len(rows)
                    rows.append(normalised)
        except OSError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="房间消息数据读取失败") from exc

        _attach_message_links(rows)
        summary = _build_summary(rows, stat.st_mtime)
        _cache_mtime_ns = stat.st_mtime_ns
        _cache_rows = rows
        _cache_summary = summary
        return _cache_rows, _cache_summary


def _normalise_row(row: dict[str, str]) -> dict[str, Any]:
    msg_type = row.get("msg_type", "")
    family = TYPE_FAMILIES.get(msg_type, "event")
    parsed = _parse_content(row)
    media_url = parsed.get("media_url") or row.get("media_url", "")
    media_kind = parsed.get("media_kind") or _media_kind_for_type(msg_type)
    media_url = _resolve_media_url(str(media_url), media_kind)

    search_text = " ".join(
        str(value)
        for value in (
            row.get("bj_time", ""),
            row.get("msg_type", ""),
            row.get("sender_name", ""),
            row.get("sender_id", ""),
            row.get("text_content", ""),
            row.get("reply_text", ""),
            row.get("gift_name", ""),
            parsed.get("title", ""),
            parsed.get("body", ""),
            parsed.get("quote", ""),
            parsed.get("detail", ""),
        )
        if value
    ).lower()

    return {
        "id": row.get("id", ""),
        "server_id": row.get("server_id", ""),
        "bj_time": row.get("bj_time", ""),
        "date": row.get("bj_time", "")[:10],
        "msg_type": msg_type,
        "type_label": TYPE_LABELS.get(msg_type, msg_type or "未知"),
        "family": family,
        "sender_name": row.get("sender_name", ""),
        "sender_id": row.get("sender_id", ""),
        "reply_to_id": row.get("reply_to_id", ""),
        "reply_text": row.get("reply_text", ""),
        "gift_name": row.get("gift_name", ""),
        "gift_count": _to_int(row.get("gift_count"), 0),
        "gift_score": row.get("gift_score", ""),
        "media_url": media_url,
        "media_kind": media_kind,
        "media_path": row.get("media_path", ""),
        "meta_path": row.get("meta_path", ""),
        "jsonl_lineno": _to_int(row.get("jsonl_lineno"), 0),
        "title": parsed.get("title", ""),
        "body": parsed.get("body", ""),
        "quote": parsed.get("quote", ""),
        "detail": parsed.get("detail", ""),
        "action_url": _safe_http_url(str(parsed.get("action_url", ""))),
        "raw_content": row.get("text_content", ""),
        "_search_text": search_text,
    }


def _parse_content(row: dict[str, str]) -> dict[str, str]:
    msg_type = row.get("msg_type", "")
    raw = row.get("text_content", "")
    data = _loads_json(raw)

    if msg_type == "TEXT":
        return {"title": "文本消息", "body": raw}

    if msg_type == "REPLY":
        info = data.get("replyInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": f"回复 {info.get('replyName', '')}".strip(),
            "body": str(info.get("text") or raw),
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
        }

    if msg_type == "AUDIO_REPLY":
        info = data.get("replyInfo", {}) if isinstance(data, dict) else {}
        duration = _to_int(info.get("duration"), 0)
        return {
            "title": f"语音回复 {info.get('replyName', '')}".strip(),
            "body": f"语音回复 {duration} 秒" if duration else "语音回复",
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
            "media_url": str(info.get("voiceUrl") or ""),
            "media_kind": "audio",
        }

    if msg_type == "GIFT_TEXT":
        parts = [row.get("gift_name", "礼物")]
        if row.get("gift_count"):
            parts.append(f"x {row.get('gift_count')}")
        return {
            "title": "送礼物",
            "body": " ".join(parts),
            "detail": f"分值 {row.get('gift_score')}" if row.get("gift_score") else "",
            "media_kind": "image",
        }

    if msg_type == "GIFTREPLY":
        info = data.get("giftReplyInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": "文字回礼物",
            "body": str(info.get("text") or raw),
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
        }

    if msg_type == "AUDIO_GIFT_REPLY":
        info = data.get("giftReplyInfo", {}) if isinstance(data, dict) else {}
        duration = _to_int(info.get("duration"), 0)
        return {
            "title": "语音回礼物",
            "body": f"语音回礼 {duration} 秒" if duration else "语音回礼",
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
            "media_url": str(info.get("voiceUrl") or ""),
            "media_kind": "audio",
        }

    if msg_type in {"AUDIO", "IMAGE", "VIDEO"}:
        duration_ms = _to_int(data.get("dur") if isinstance(data, dict) else 0, 0)
        duration = round(duration_ms / 1000) if duration_ms > 1000 else duration_ms
        title = TYPE_LABELS.get(msg_type, msg_type)
        detail_parts = []
        if isinstance(data, dict):
            if data.get("w") and data.get("h"):
                detail_parts.append(f"{data.get('w')} x {data.get('h')}")
            if duration:
                detail_parts.append(f"{duration} 秒")
        return {
            "title": title,
            "body": title,
            "detail": " · ".join(detail_parts),
            "media_kind": _media_kind_for_type(msg_type),
        }

    if msg_type == "EXPRESSIMAGE":
        info = data.get("expressImgInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": "表情包",
            "body": "表情包",
            "detail": _size_detail(info),
            "media_kind": "image",
        }

    if msg_type == "LIVEPUSH":
        info = data.get("livePushInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": str(info.get("liveTitle") or "直播推送"),
            "body": f"直播 ID {info.get('liveId')}" if info.get("liveId") else "直播推送",
            "action_url": str(info.get("shortPath") or ""),
            "media_kind": "image",
        }

    if msg_type.startswith("FLIPCARD"):
        info = data.get("filpCardInfo", {}) if isinstance(data, dict) else {}
        answer = info.get("answer", "")
        answer_data = _loads_json(answer) if isinstance(answer, str) else {}
        media_url = answer_data.get("url", "") if isinstance(answer_data, dict) else ""
        media_kind = "audio" if msg_type == "FLIPCARD_AUDIO" else "video" if msg_type == "FLIPCARD_VIDEO" else ""
        duration = _to_int(answer_data.get("duration") if isinstance(answer_data, dict) else 0, 0)
        return {
            "title": TYPE_LABELS.get(msg_type, "翻牌"),
            "body": str(answer if msg_type == "FLIPCARD" else f"{TYPE_LABELS.get(msg_type, '翻牌')} {duration} 秒").strip(),
            "quote": str(info.get("question") or ""),
            "detail": f"问题 ID {info.get('questionId')}" if info.get("questionId") else "",
            "media_url": str(media_url),
            "media_kind": media_kind,
        }

    if msg_type == "SHARE_POSTS":
        info = data.get("shareInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": str(info.get("shareTitle") or "动态分享"),
            "body": str(info.get("shareDesc") or ""),
            "media_url": str(info.get("sharePic") or ""),
            "media_kind": "image",
            "action_url": str(info.get("jumpPath") or ""),
        }

    if msg_type == "RED_PACKET_2026":
        return {
            "title": "红包",
            "body": str(data.get("blessMessage") or "红包消息") if isinstance(data, dict) else raw,
            "detail": f"来自 {data.get('creatorName')}" if isinstance(data, dict) and data.get("creatorName") else "",
            "media_url": str(data.get("coverUrl") or "") if isinstance(data, dict) else "",
            "media_kind": "image",
        }

    return {"title": TYPE_LABELS.get(msg_type, msg_type), "body": raw}


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    msg_type: str,
    families: set[str] | None,
    sender: str,
    keyword: str,
    has_media: str,
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    sender_lower = sender.lower()
    keyword_lower = keyword.lower()
    filtered: list[dict[str, Any]] = []

    for row in rows:
        if msg_type != "ALL" and row["msg_type"] != msg_type:
            continue
        if families is not None and row["family"] not in families:
            continue
        if sender_lower and sender_lower not in row["sender_name"].lower():
            continue
        if keyword_lower and keyword_lower not in row["_search_text"]:
            continue
        if has_media == "with" and not row["media_url"] and not row["media_path"]:
            continue
        if has_media == "without" and (row["media_url"] or row["media_path"]):
            continue
        if date_from and row["date"] < date_from:
            continue
        if date_to and row["date"] > date_to:
            continue
        filtered.append(row)
    return filtered


def _is_unfiltered(
    *,
    msg_type: str,
    families: set[str] | None,
    sender: str,
    keyword: str,
    has_media: str,
    date_from: str,
    date_to: str,
) -> bool:
    return (
        msg_type == "ALL"
        and families is None
        and not sender
        and not keyword
        and has_media == "all"
        and not date_from
        and not date_to
    )


def _parse_families(value: str) -> set[str] | None:
    parts = {part.strip().lower() for part in (value or "all").split(",") if part.strip()}
    if not parts or "all" in parts:
        return None
    invalid = parts - VALID_FAMILIES
    if invalid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的消息分组")
    return parts


def _chunk_end(total: int, before_index: int | None, target_index: int | None) -> int:
    if target_index is not None:
        return min(total, target_index + 1)
    return total if before_index is None else min(before_index, total)


def _find_row_index(rows: list[dict[str, Any]], message_id: str) -> int | None:
    if not message_id:
        return None
    for idx, row in enumerate(rows):
        if row.get("id") == message_id:
            return idx
    return None


def _attach_message_links(rows: list[dict[str, Any]]) -> None:
    rows_by_id = {str(row.get("id", "")): row for row in rows if row.get("id")}
    reply_ids_by_gift: dict[str, list[str]] = {}
    for row in rows:
        reply_to_id = str(row.get("reply_to_id", ""))
        if reply_to_id and reply_to_id in rows_by_id:
            row["reply_target"] = _reply_target(rows_by_id[reply_to_id])
        if row.get("family") == "gift_reply" and row.get("reply_to_id") and row.get("id"):
            reply_ids_by_gift.setdefault(str(row["reply_to_id"]), []).append(str(row["id"]))

    for row in rows:
        if row.get("family") == "gift":
            reply_ids = reply_ids_by_gift.get(str(row.get("id", "")), [])
            row["reply_message_ids"] = reply_ids
            row["reply_count"] = len(reply_ids)
        elif row.get("family") == "gift_reply":
            row["gift_message_id"] = row.get("reply_to_id", "")


def _reply_target(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "bj_time": row.get("bj_time", ""),
        "sender_name": row.get("sender_name", ""),
        "sender_id": row.get("sender_id", ""),
        "msg_type": row.get("msg_type", ""),
        "type_label": row.get("type_label", ""),
        "family": row.get("family", ""),
        "title": row.get("title", ""),
        "body": row.get("body", ""),
        "gift_name": row.get("gift_name", ""),
        "gift_count": row.get("gift_count", 0),
        "media_url": row.get("media_url", ""),
        "media_kind": row.get("media_kind", ""),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _build_summary(rows: list[dict[str, Any]], mtime: float) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    for row in rows:
        type_counts[row["msg_type"]] = type_counts.get(row["msg_type"], 0) + 1
        family_counts[row["family"]] = family_counts.get(row["family"], 0) + 1

    return {
        "total_messages": len(rows),
        "first_bj_time": rows[0]["bj_time"] if rows else "",
        "latest_bj_time": rows[-1]["bj_time"] if rows else "",
        "source_path": str(_data_path()),
        "source_mtime": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "type_kinds": len(type_counts),
        "latest_unreplied_gift_batch": _latest_unreplied_gift_batch(rows),
        "type_counts": [
            {
                "msg_type": msg_type,
                "label": TYPE_LABELS.get(msg_type, msg_type),
                "family": TYPE_FAMILIES.get(msg_type, "event"),
                "count": count,
            }
            for msg_type, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "family_counts": [
            {"family": family, "label": _family_label(family), "count": count}
            for family, count in sorted(family_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _latest_unreplied_gift_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gift_rows = [row for row in rows if row.get("family") == "gift"]
    batch_end_index = None
    for idx in range(len(gift_rows) - 1, -1, -1):
        if _is_unreplied_gift(gift_rows[idx]):
            batch_end_index = idx
            break

    if batch_end_index is None:
        return {
            "start_message_id": "",
            "start_bj_time": "",
            "end_message_id": "",
            "end_bj_time": "",
            "count": 0,
        }

    batch_start_index = batch_end_index
    while batch_start_index > 0 and _is_unreplied_gift(gift_rows[batch_start_index - 1]):
        batch_start_index -= 1

    start = gift_rows[batch_start_index]
    end = gift_rows[batch_end_index]
    return {
        "start_message_id": start.get("id", ""),
        "start_bj_time": start.get("bj_time", ""),
        "end_message_id": end.get("id", ""),
        "end_bj_time": end.get("bj_time", ""),
        "count": batch_end_index - batch_start_index + 1,
    }


def _is_unreplied_gift(row: dict[str, Any]) -> bool:
    return row.get("family") == "gift" and int(row.get("reply_count") or 0) == 0


def _loads_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip().startswith("{"):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _media_kind_for_type(msg_type: str) -> str:
    if msg_type in {"IMAGE", "EXPRESSIMAGE", "GIFT_TEXT", "LIVEPUSH", "SHARE_POSTS", "RED_PACKET_2026"}:
        return "image"
    if msg_type in {"AUDIO", "AUDIO_REPLY", "AUDIO_GIFT_REPLY", "FLIPCARD_AUDIO"}:
        return "audio"
    if msg_type in {"VIDEO", "FLIPCARD_VIDEO"}:
        return "video"
    return ""


def _resolve_media_url(value: str, media_kind: str) -> str:
    value = _safe_http_url(value)
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not value.startswith("/"):
        return ""
    if media_kind in {"audio", "video"}:
        return "https://mp4-new1.48.cn" + value
    return "https://source3.48.cn" + value


def _safe_http_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://") or value.startswith("/"):
        return value
    return ""


def _family_label(family: str) -> str:
    return {
        "text": "文本",
        "reply": "回复",
        "gift": "礼物",
        "gift_reply": "回礼物",
        "media": "媒体",
        "flipcard": "翻牌",
        "live": "直播",
        "share": "分享",
        "event": "事件",
    }.get(family, family)


def _size_detail(info: dict[str, Any]) -> str:
    if info.get("width") and info.get("height"):
        return f"{info.get('width')} x {info.get('height')}"
    if info.get("w") and info.get("h"):
        return f"{info.get('w')} x {info.get('h')}"
    return ""


def _validate_date(label: str, value: str) -> None:
    if value and not DATE_RE.match(value.strip()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{label} 日期格式应为 YYYY-MM-DD")


def _to_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

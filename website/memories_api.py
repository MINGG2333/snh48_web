"""
Memories API router.

Stores and serves "memory" records about Chen Jiayi and fans. The page is
password-protected, avoids ranking fans, and keeps platform IDs in backend data
instead of exposing them to normal visitors.
"""
from __future__ import annotations

import hmac
import json
import re
import tempfile
import threading
import uuid
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from website import config as cfg
from website.rate_limiter import (
    check_admin_login_limit,
    check_memories_submit_limit,
    get_client_ip,
)

router = APIRouter(prefix="/api/memories", tags=["记忆页"])

MEMORY_TYPES = {
    "idol_reply": "小偶像回应粉丝",
    "fan_expression": "粉丝表达喜欢",
    "fan_work": "粉丝为她做的事",
    "shared_memory": "共同记忆",
    "private_interaction": "私密或半私密互动",
}

PLATFORMS = {
    "pocket48": "口袋48",
    "weibo": "微博",
    "bilibili": "B站",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "youtube": "YouTube",
    "fanclub": "应援会",
    "offline": "线下",
    "other": "其他",
}

AUDIT_STATUSES = {
    "auto_approved": "基础审核通过",
    "approved": "人工审核通过",
    "pending_manual": "待人工审核",
    "rejected": "已拒绝",
}

CONFIRMATION_STATUSES = {
    "unconfirmed": "待确认",
    "fanclub_confirmed": "应援会确认",
    "idol_confirmed": "本人确认",
}

VALID_PRIVACY_LEVELS = {"public", "soft_private"}
VALID_REVIEW_ACTIONS = {
    "approve",
    "reject",
    "hide",
    "confirm_fanclub",
    "confirm_idol",
    "unconfirm",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
URL_RE = re.compile(r"https?://", re.IGNORECASE)
REPEATED_RE = re.compile(r"(.)\1{12,}")
SUSPICIOUS_TERMS = (
    "傻逼",
    "煞笔",
    "去死",
    "滚出",
    "诈骗",
    "加微信",
    "加qq",
    "代刷",
)

_store_lock = threading.Lock()


class MemorySubmitRequest(BaseModel):
    memory_type: str
    title: str
    occurred_at: str = ""
    summary: str
    public_note: str = ""
    actor_display_name: str = ""
    actor_platform: str = "other"
    source_url: str = ""
    source_label: str = ""
    evidence_note: str = ""
    privacy_level: str = "public"
    tags: list[str] = Field(default_factory=list)

    @field_validator("memory_type")
    @classmethod
    def validate_memory_type(cls, value: str) -> str:
        value = value.strip()
        if value not in MEMORY_TYPES:
            raise ValueError("无效的记忆类型")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _require_text(value, "标题", 2, 80)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return _require_text(value, "记忆内容", 8, 1200)

    @field_validator("public_note", "evidence_note")
    @classmethod
    def validate_optional_long_text(cls, value: str) -> str:
        return _clean_text(value, max_length=1200)

    @field_validator("actor_display_name", "source_label")
    @classmethod
    def validate_optional_short_text(cls, value: str) -> str:
        return _clean_text(value, max_length=80)

    @field_validator("actor_platform")
    @classmethod
    def validate_actor_platform(cls, value: str) -> str:
        value = value.strip() or "other"
        if value not in PLATFORMS:
            raise ValueError("无效的平台")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _clean_url(value)

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: str) -> str:
        value = _clean_text(value, max_length=32)
        if value and not DATE_RE.match(value):
            raise ValueError("时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")
        if value and value[:10] < cfg.MEMORIES_START_DATE:
            raise ValueError(f"记忆时间不能早于 {cfg.MEMORIES_START_DATE}")
        return value.replace("T", " ")

    @field_validator("privacy_level")
    @classmethod
    def validate_privacy_level(cls, value: str) -> str:
        value = value.strip() or "public"
        if value not in VALID_PRIVACY_LEVELS:
            raise ValueError("无效的隐私级别")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        tags: list[str] = []
        for item in value[:8]:
            text = _clean_text(str(item), max_length=20)
            if text and text not in tags:
                tags.append(text)
        return tags


class MemoryReviewRequest(BaseModel):
    id: str
    action: str
    reason: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 80:
            raise ValueError("无效的记忆 ID")
        return value

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        value = value.strip()
        if value not in VALID_REVIEW_ACTIONS:
            raise ValueError("无效的操作")
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _clean_text(value, max_length=300)


@router.get("/data")
def get_memories_data(
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    memory_type: str = Query("all"),
    actor_platform: str = Query("all"),
    confirmation_status: str = Query("all"),
    q: str = Query(""),
):
    """Return public memory records after view-password verification."""
    _verify_password_value(
        request=request,
        expected=cfg.MEMORIES_VIEW_PASSWORD,
        provided=request.headers.get("X-Memories-Password"),
        disabled_detail="记忆页未启用",
        missing_detail="需要记忆页密码",
        wrong_detail="记忆页密码错误",
    )
    response.headers["Cache-Control"] = "no-store"
    records = _filter_records(
        _load_items(),
        public_only=True,
        memory_type=memory_type,
        actor_platform=actor_platform,
        confirmation_status=confirmation_status,
        q=q,
    )
    return _page_response(records, page, page_size, include_private_id=False)


@router.get("/manage")
def get_memories_manage_data(
    request: Request,
    response: Response,
    mode: str = Query("fanclub"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    memory_type: str = Query("all"),
    audit_status: str = Query("all"),
    confirmation_status: str = Query("all"),
    q: str = Query(""),
):
    """Return manager-visible records for fanclub or idol mode."""
    mode = mode.strip().lower()
    if mode == "idol":
        _verify_idol_request(request)
        records = [
            item for item in _load_items()
            if item.get("visibility") == "public"
            and item.get("audit_status") != "rejected"
        ]
    elif mode == "fanclub":
        _verify_fanclub_request(request)
        records = _load_items()
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的管理模式")

    response.headers["Cache-Control"] = "no-store"
    filtered = _filter_records(
        records,
        public_only=False,
        memory_type=memory_type,
        actor_platform="all",
        audit_status=audit_status,
        confirmation_status=confirmation_status,
        q=q,
    )
    return _page_response(filtered, page, page_size, include_private_id=(mode == "fanclub"))


@router.post("/submit")
def submit_memory(
    req: MemorySubmitRequest,
    request: Request,
    x_memories_password: str = Header(None, alias="X-Memories-Password"),
):
    """Submit a new memory for basic review and display/queueing."""
    _verify_password_value(
        request=request,
        expected=cfg.MEMORIES_VIEW_PASSWORD,
        provided=x_memories_password,
        disabled_detail="记忆页未启用",
        missing_detail="需要记忆页密码",
        wrong_detail="记忆页密码错误",
    )
    if not cfg.MEMORIES_SUBMIT_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前服务器暂不开放记忆提交")

    check_memories_submit_limit(get_client_ip(request))
    record = _record_from_submission(req)
    with _store_lock:
        store = _load_store()
        items = store.setdefault("items", [])
        items.append(record)
        _save_store(store)

    return {
        "success": True,
        "item": _public_record(record, include_private_id=False),
        "message": "记忆已记录。通过基础审核的内容会先展示为待确认；需要人工审核的内容会先隐藏。",
    }


@router.post("/review")
def review_memory(req: MemoryReviewRequest, request: Request):
    """Review or confirm a memory record."""
    if req.action == "confirm_idol":
        actor = "idol"
        _verify_idol_request(request)
    else:
        actor = "fanclub"
        _verify_fanclub_request(request)

    with _store_lock:
        store = _load_store()
        item = _find_item(store.get("items", []), req.id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记忆不存在")
        _apply_review_action(item, req.action, req.reason, actor)
        _save_store(store)
        updated = _public_record(item, include_private_id=(actor == "fanclub"))
    return {"success": True, "item": updated}


def _verify_password_value(
    *,
    request: Request,
    expected: str,
    provided: str | None,
    disabled_detail: str,
    missing_detail: str,
    wrong_detail: str,
) -> None:
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=disabled_detail)
    if not provided:
        check_admin_login_limit(get_client_ip(request), missing_detail)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=missing_detail)
    if not hmac.compare_digest(expected, provided):
        check_admin_login_limit(get_client_ip(request), wrong_detail)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=wrong_detail)


def _verify_fanclub_request(request: Request) -> None:
    _verify_password_value(
        request=request,
        expected=cfg.MEMORIES_FANCLUB_PASSWORD,
        provided=request.headers.get("X-Memories-Fanclub-Password"),
        disabled_detail="应援会模式未启用",
        missing_detail="需要应援会模式密码",
        wrong_detail="应援会模式密码错误",
    )


def _verify_idol_request(request: Request) -> None:
    _verify_password_value(
        request=request,
        expected=cfg.MEMORIES_IDOL_PASSWORD,
        provided=request.headers.get("X-Memories-Idol-Password"),
        disabled_detail="本人模式未启用",
        missing_detail="需要本人模式密码",
        wrong_detail="本人模式密码错误",
    )


def _data_path() -> Path:
    return Path(cfg.MEMORIES_DATA_PATH)


def _load_store() -> dict[str, Any]:
    path = _data_path()
    if not path.exists():
        return {"version": 1, "updated_at": "", "items": []}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="记忆数据读取失败") from exc
    if not isinstance(doc, dict):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="记忆数据格式错误")
    items = doc.get("items")
    if not isinstance(items, list):
        doc["items"] = []
    return doc


def _save_store(store: dict[str, Any]) -> None:
    path = _data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    store["version"] = 1
    store["updated_at"] = _now()
    content = json.dumps(store, ensure_ascii=False, indent=2)
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as f:
            f.write(content)
            f.write("\n")
            tmp_name = f.name
        Path(tmp_name).replace(path)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="记忆数据保存失败") from exc


def _load_items() -> list[dict[str, Any]]:
    return list(_load_store().get("items", []))


def _find_item(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if str(item.get("id", "")) == item_id:
            return item
    return None


def _filter_records(
    records: list[dict[str, Any]],
    *,
    public_only: bool,
    memory_type: str,
    actor_platform: str,
    audit_status: str = "all",
    confirmation_status: str,
    q: str,
) -> list[dict[str, Any]]:
    memory_type = memory_type.strip() or "all"
    actor_platform = actor_platform.strip() or "all"
    audit_status = audit_status.strip() or "all"
    confirmation_status = confirmation_status.strip() or "all"
    query = _clean_text(q, max_length=80).lower()

    if memory_type != "all" and memory_type not in MEMORY_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的记忆类型")
    if actor_platform != "all" and actor_platform not in PLATFORMS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的平台")
    if audit_status != "all" and audit_status not in AUDIT_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的审核状态")
    if confirmation_status != "all" and confirmation_status not in CONFIRMATION_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的确认状态")

    output: list[dict[str, Any]] = []
    for item in records:
        if public_only and not _is_public_item(item):
            continue
        if memory_type != "all" and item.get("memory_type") != memory_type:
            continue
        actor = item.get("actor") if isinstance(item.get("actor"), dict) else {}
        if actor_platform != "all" and actor.get("platform") != actor_platform:
            continue
        if audit_status != "all" and item.get("audit_status") != audit_status:
            continue
        if confirmation_status != "all" and item.get("confirmation_status") != confirmation_status:
            continue
        if query and query not in _search_text(item):
            continue
        output.append(item)
    output.sort(key=_sort_key, reverse=True)
    return output


def _is_public_item(item: dict[str, Any]) -> bool:
    return (
        item.get("visibility") == "public"
        and item.get("audit_status") != "rejected"
        and item.get("memory_type") in MEMORY_TYPES
    )


def _search_text(item: dict[str, Any]) -> str:
    actor = item.get("actor") if isinstance(item.get("actor"), dict) else {}
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    fields = [
        item.get("title", ""),
        item.get("summary", ""),
        item.get("public_note", ""),
        actor.get("display_name", ""),
        actor.get("platform_label", ""),
        source.get("label", ""),
        " ".join(item.get("tags", []) if isinstance(item.get("tags"), list) else []),
    ]
    return "\n".join(str(value).lower() for value in fields)


def _sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("occurred_at", "")),
        str(item.get("created_at", "")),
        str(item.get("id", "")),
    )


def _page_response(
    records: list[dict[str, Any]],
    page: int,
    page_size: int,
    *,
    include_private_id: bool,
) -> dict[str, Any]:
    total = len(records)
    total_pages = max(1, ceil(total / page_size))
    start = (page - 1) * page_size
    end = start + page_size
    public_records = [_public_record(item, include_private_id=include_private_id) for item in records]
    all_public = [item for item in _load_items() if _is_public_item(item)]
    return {
        "items": public_records[start:end],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "summary": _summary(all_public),
        "memory_types": _options(MEMORY_TYPES),
        "platforms": _options(PLATFORMS),
        "audit_statuses": _options(AUDIT_STATUSES),
        "confirmation_statuses": _options(CONFIRMATION_STATUSES),
        "updated_at": _load_store().get("updated_at", ""),
        "start_date": cfg.MEMORIES_START_DATE,
        "submit_enabled": cfg.MEMORIES_SUBMIT_ENABLED,
    }


def _public_record(item: dict[str, Any], *, include_private_id: bool) -> dict[str, Any]:
    actor = item.get("actor") if isinstance(item.get("actor"), dict) else {}
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    public_actor = {
        "display_name": str(actor.get("display_name", "")),
        "platform": str(actor.get("platform", "other")),
        "platform_label": str(actor.get("platform_label", PLATFORMS.get(str(actor.get("platform", "other")), "其他"))),
    }
    if include_private_id:
        public_actor["platform_id"] = str(actor.get("platform_id", ""))
    return {
        "id": str(item.get("id", "")),
        "memory_type": str(item.get("memory_type", "")),
        "memory_type_label": MEMORY_TYPES.get(str(item.get("memory_type", "")), str(item.get("memory_type", ""))),
        "title": str(item.get("title", "")),
        "occurred_at": str(item.get("occurred_at", "")),
        "summary": str(item.get("summary", "")),
        "public_note": str(item.get("public_note", "")),
        "actor": public_actor,
        "source": {
            "kind": str(source.get("kind", "")),
            "label": str(source.get("label", "")),
            "url": _safe_public_url(str(source.get("url", ""))),
        },
        "media": {
            "image_url": _safe_public_url(str(media.get("image_url", ""))),
            "thumbnail_url": _safe_public_url(str(media.get("thumbnail_url", ""))),
        },
        "privacy_level": str(item.get("privacy_level", "public")),
        "evidence_public": bool(item.get("evidence_public", False)),
        "tags": [str(tag) for tag in item.get("tags", []) if str(tag).strip()][:8],
        "audit_status": str(item.get("audit_status", "pending_manual")),
        "audit_status_label": AUDIT_STATUSES.get(str(item.get("audit_status", "")), str(item.get("audit_status", ""))),
        "audit_reason": str(item.get("audit_reason", "")),
        "visibility": str(item.get("visibility", "pending")),
        "confirmation_status": str(item.get("confirmation_status", "unconfirmed")),
        "confirmation_status_label": CONFIRMATION_STATUSES.get(
            str(item.get("confirmation_status", "unconfirmed")),
            str(item.get("confirmation_status", "unconfirmed")),
        ),
        "confirmed_by": str(item.get("confirmed_by", "")),
        "confirmed_at": str(item.get("confirmed_at", "")),
        "created_by": str(item.get("created_by", "")),
        "created_at": str(item.get("created_at", "")),
        "updated_at": str(item.get("updated_at", "")),
    }


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = {key: 0 for key in MEMORY_TYPES}
    by_platform: dict[str, int] = {}
    by_confirmation = {key: 0 for key in CONFIRMATION_STATUSES}
    pending_confirmation = 0
    for item in records:
        memory_type = str(item.get("memory_type", ""))
        if memory_type in by_type:
            by_type[memory_type] += 1
        actor = item.get("actor") if isinstance(item.get("actor"), dict) else {}
        platform = str(actor.get("platform", "other") or "other")
        by_platform[platform] = by_platform.get(platform, 0) + 1
        confirmation = str(item.get("confirmation_status", "unconfirmed"))
        if confirmation in by_confirmation:
            by_confirmation[confirmation] += 1
        if confirmation == "unconfirmed":
            pending_confirmation += 1
    return {
        "total_public": len(records),
        "by_type": [
            {"key": key, "label": label, "count": by_type[key]}
            for key, label in MEMORY_TYPES.items()
        ],
        "by_platform": [
            {"key": key, "label": PLATFORMS.get(key, key), "count": count}
            for key, count in sorted(by_platform.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
        "by_confirmation": [
            {"key": key, "label": label, "count": by_confirmation[key]}
            for key, label in CONFIRMATION_STATUSES.items()
        ],
        "pending_confirmation": pending_confirmation,
    }


def _options(mapping: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label in mapping.items()]


def _record_from_submission(req: MemorySubmitRequest) -> dict[str, Any]:
    audit_status, audit_reason, visibility = _basic_review(req)
    now = _now()
    memory_type = req.memory_type
    privacy_level = req.privacy_level
    if memory_type == "private_interaction" and privacy_level == "public":
        privacy_level = "soft_private"
    source_label = req.source_label or "粉丝登记"
    return {
        "id": _new_memory_id(),
        "memory_type": memory_type,
        "title": req.title,
        "occurred_at": req.occurred_at,
        "summary": req.summary,
        "public_note": req.public_note or req.evidence_note,
        "actor": {
            "display_name": req.actor_display_name,
            "platform": req.actor_platform,
            "platform_label": PLATFORMS.get(req.actor_platform, "其他"),
            "platform_id": "",
        },
        "source": {
            "kind": "fan_submission",
            "label": source_label,
            "url": req.source_url,
            "external_id": "",
        },
        "media": {
            "image_url": "",
            "thumbnail_url": "",
        },
        "privacy_level": privacy_level,
        "evidence_public": bool(req.source_url or req.evidence_note),
        "tags": req.tags,
        "audit_status": audit_status,
        "audit_reason": audit_reason,
        "visibility": visibility,
        "confirmation_status": "unconfirmed",
        "confirmed_by": "",
        "confirmed_at": "",
        "created_by": "fan_submission",
        "created_at": now,
        "updated_at": now,
    }


def _basic_review(req: MemorySubmitRequest) -> tuple[str, str, str]:
    text = "\n".join([req.title, req.summary, req.public_note, req.evidence_note]).lower()
    reasons: list[str] = []
    if any(term in text for term in SUSPICIOUS_TERMS):
        reasons.append("包含疑似恶意或广告词")
    if len(URL_RE.findall(text)) > 3:
        reasons.append("正文链接过多")
    if REPEATED_RE.search(text):
        reasons.append("存在异常重复字符")
    if req.memory_type == "private_interaction" and len(req.summary) > 500:
        reasons.append("私密互动自述较长，建议人工确认公开边界")
    if reasons:
        return "pending_manual", "；".join(reasons), "pending"
    return "auto_approved", "基础规则通过", "public"


def _apply_review_action(item: dict[str, Any], action: str, reason: str, actor: str) -> None:
    now = _now()
    if action == "approve":
        item["audit_status"] = "approved"
        item["audit_reason"] = reason or "人工审核通过"
        item["visibility"] = "public"
    elif action == "reject":
        item["audit_status"] = "rejected"
        item["audit_reason"] = reason or "人工审核拒绝"
        item["visibility"] = "hidden"
    elif action == "hide":
        item["visibility"] = "hidden"
        item["audit_reason"] = reason or "人工隐藏"
    elif action == "confirm_fanclub":
        item["confirmation_status"] = "fanclub_confirmed"
        item["confirmed_by"] = "fanclub"
        item["confirmed_at"] = now
    elif action == "confirm_idol":
        item["confirmation_status"] = "idol_confirmed"
        item["confirmed_by"] = "idol"
        item["confirmed_at"] = now
    elif action == "unconfirm":
        item["confirmation_status"] = "unconfirmed"
        item["confirmed_by"] = ""
        item["confirmed_at"] = ""
    item["updated_at"] = now
    item["last_reviewed_by"] = actor
    item["last_reviewed_at"] = now


def _require_text(value: str, label: str, min_length: int, max_length: int) -> str:
    value = _clean_text(value, max_length=max_length)
    if len(value) < min_length:
        raise ValueError(f"{label}不能少于{min_length}个字")
    return value


def _clean_text(value: str, *, max_length: int) -> str:
    value = CONTROL_RE.sub("", str(value or "")).strip()
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value[:max_length]


def _clean_url(value: str) -> str:
    value = _clean_text(value, max_length=500)
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("来源链接只支持 http 或 https")
    return value


def _safe_public_url(value: str) -> str:
    if not value:
        return ""
    try:
        return _clean_url(value)
    except ValueError:
        return ""


def _new_memory_id() -> str:
    return f"MEM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

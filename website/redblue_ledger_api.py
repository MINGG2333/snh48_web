"""红蓝计分台账 2026 API.

数据由房间/直播计分、微店订单和手动暗票组成。台账本身走 shared_runtime_state
版本化复制；微店拉单/无需物流发货和 Codex 昵称分析通过本机 root worker 队列执行。
"""
from __future__ import annotations

import fcntl
import hmac
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, Body, Cookie, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from website import config as cfg
from website import identity_index
from website import password_session
from website.rate_limiter import check_redblue_login_limit as _check_redblue_login_limit
from website.rate_limiter import get_client_ip
from website.shared_runtime_state import (
    SharedStateError,
    SharedStatePeerError,
    execute_mutation,
    load_document,
    peer_command,
    register_mutator,
)

router = APIRouter(prefix="/api/redblue", tags=["红蓝计分台账 2026"])

logger = logging.getLogger(__name__)

BJ_TZ = timezone(timedelta(hours=8))
RESOURCE = "redblue_ledger"
VALID_SOURCES = {"manual", "weidian", "association_manual", "weidian_manual", "room", "live"}
SOURCE_LABELS = {
    "manual": "暗票",
    "weidian": "微店",
    "association_manual": "手动",
    "weidian_manual": "手动",
    "room": "房间",
    "live": "直播",
}
DEFAULT_SCORING_METHODS = {
    "manual": "计分卡",
    "weidian": "鸡腿",
    "association_manual": "鸡腿",
    "weidian_manual": "鸡腿",
    "room": "计分卡",
    "live": "计分卡",
}
SCORING_SOURCE_LABELS = {
    "manual": "暗票",
    "weidian": "应援会（微店）",
    "association_manual": "手动",
    "weidian_manual": "手动",
    "room": "房间",
    "live": "直播",
}
SCORING_METHODS = ("计分卡", "鸡腿")
# 应援会来源（微店/应援会手动）使用独立的履约状态；已投保留给未来使用。
ASSOCIATION_SOURCES = {"weidian", "association_manual", "weidian_manual"}
ENTRY_STATUS_LABELS = {
    "unshipped": "未发货",
    "shipped": "已发货",
    "paid": "已付款",
    "settled": "已投",
    "pending": "待投",
}
ENTRY_STATUS_BY_SOURCE = {
    "weidian": ("unshipped", "shipped", "settled"),
    "association_manual": ("paid", "settled"),
    "weidian_manual": ("paid", "settled"),
}
EVIDENCE_DIR = Path(
    getattr(
        cfg,
        "REDBLUE_SCORING_EVIDENCE_DIR",
        Path(cfg.PROJECT_ROOT).parent
        / "snh48-fan-hub"
        / "private_handover"
        / "web_state"
        / "redblue_scoring_evidence",
    )
)
EVIDENCE_MAX_BYTES = 8 * 1024 * 1024
EVIDENCE_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
EVIDENCE_NAME_RE = re.compile(r"^[a-f0-9]{32}\.(?:jpg|png|gif|webp)$")
DAILY_SCORING_CATEGORIES = (
    {"key": "room|计分卡", "label": "房间·计分卡", "source": "room", "method": "计分卡"},
    {"key": "room|鸡腿", "label": "房间·鸡腿", "source": "room", "method": "鸡腿"},
    {"key": "live|计分卡", "label": "直播·计分卡", "source": "live", "method": "计分卡"},
    {"key": "live|鸡腿", "label": "直播·鸡腿", "source": "live", "method": "鸡腿"},
    {"key": "weidian|鸡腿", "label": "应援会·鸡腿（微店）", "source": "weidian", "method": "鸡腿"},
    {"key": "association_manual|鸡腿", "label": "应援会·鸡腿（手动）", "source": "association_manual", "method": "鸡腿"},
    {"key": "manual|计分卡", "label": "暗票·计分卡", "source": "manual", "method": "计分卡"},
)
DAILY_SCORING_KEYS = {item["key"] for item in DAILY_SCORING_CATEGORIES}
BUSINESS_OPTION_GROUPS = (
    (
        "card",
        "甲鱼回馈（计分卡）",
        (
            (1, "方言盲盒"),
            (1, "点播 BGM"),
            (3, "答案之书"),
            (3, "绕口令"),
            (3, "点唱半首"),
            (3, "点歌盲盒"),
            (6, "点唱整首"),
            (6, "查水表"),
            (6, "re 视频"),
            (6, "河曲朗诵"),
            (6, "简笔画头像"),
            (6, "ID 合影"),
            (9, "公演 MC 开场白"),
            (9, "歌词卡"),
            (9, "成语接龙"),
            (18, "公演 MC 指定动作"),
            (18, "公演跳半首"),
            (18, "换口袋头像或背景两天"),
            (27, "跳公演"),
            (27, "公演定制造型"),
            (48, "舞蹈房半首"),
            (99, "舞蹈房整首"),
        ),
    ),
    (
        "bonus",
        "鸡腿计分加赠",
        (
            (3, "方言盲盒"),
            (6, "答案之书"),
            (9, "答案之书"),
            (18, "点唱整首"),
            (27, "公演 MC 开场白"),
            (48, "公演 MC 指定动作"),
            (99, "跳公演"),
        ),
    ),
)
BUSINESS_OPTIONS = [
    {
        "value": f"{score}-{name}",
        "label": f"{score}-{name}",
        "score": score,
        "name": name,
        "group": group_key,
        "group_label": group_label,
    }
    for group_key, group_label, items in BUSINESS_OPTION_GROUPS
    for score, name in items
]
BUSINESS_OPTION_VALUES = {item["value"] for item in BUSINESS_OPTIONS}
BUSINESS_OPTION_MAP = {item["value"]: item for item in BUSINESS_OPTIONS}
BONUS_OPTION_MAP = {item["value"]: item for item in BUSINESS_OPTIONS if item["group"] == "bonus"}
BUSINESS_GROUP_VALUES = {
    group_key: {f"{score}-{name}" for score, name in items}
    for group_key, _group_label, items in BUSINESS_OPTION_GROUPS
}
WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")
TEXT_LIMIT = 500
JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")
POCKET_ID_RE = re.compile(r"(?<!\d)(\d{4,12})(?!\d)")
MUTATION_HEADER = "X-Redblue-Operation-Id"
AUTH_COOKIE = "redblue_ledger_auth"
AUTH_COOKIE_MAX_AGE = password_session.cookie_max_age()


class LoginRequest(BaseModel):
    password: str


def _cookie_token(password: str) -> str:
    return password_session.cookie_token(password, context="redblue")


def _now() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d")


def _clean(value: Any, limit: int = TEXT_LIMIT) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _weidian_order_score(order: dict[str, Any]) -> float:
    """红蓝计分：优先用 worker 的 score；否则总价 / 26.25，最后回退 quantity。"""
    explicit = _to_float(order.get("score"), -1.0)
    if explicit >= 0:
        return round(explicit, 4)
    amount = _to_float(order.get("amount"), 0.0)
    if amount > 0:
        unit_price = max(_to_float(getattr(cfg, "REDBLUE_WEIDIAN_UNIT_PRICE", 26.25), 26.25), 0.01)
        return round(amount / unit_price, 4)
    return round(_to_float(order.get("quantity"), 0.0), 4)


def _weidian_order_shipped(order: dict[str, Any]) -> bool:
    status_desc = _clean(order.get("status"), 40)
    return bool(order.get("shipped")) or any(
        keyword in status_desc for keyword in ("已发货", "交易成功", "完成")
    )


def _entry_status(entry: dict[str, Any]) -> str:
    """条目履约状态。

    微店/手动（应援会来源）用未发货、已发货、已付款、已投；
    房间/直播沿用原“已投/待投”结算状态。
    """
    source = _clean(entry.get("source"), 20)
    status = _clean(entry.get("status"), 20).lower()
    allowed = ENTRY_STATUS_BY_SOURCE.get(source)
    if allowed:
        if status in allowed:
            return status
        if source == "weidian":
            weidian = entry.get("weidian") if isinstance(entry.get("weidian"), dict) else {}
            shipped = bool(weidian.get("shipped")) or any(
                keyword in _clean(weidian.get("status"), 40)
                for keyword in ("已发货", "交易成功", "完成")
            )
            return "shipped" if shipped else "unshipped"
        return "paid"
    return "settled" if bool(entry.get("settled")) else "pending"


def _entry_settled(entry: dict[str, Any]) -> bool:
    return _entry_status(entry) == "settled"


def _settlement_block(doc: dict[str, Any]) -> dict[str, Any]:
    block = doc.get("association_settlement")
    if not isinstance(block, dict):
        block = {}
    remainder = block.get("remainder")
    if not isinstance(remainder, dict):
        remainder = {}
    block["remainder"] = remainder
    return block


def _settlement_remainder(doc: dict[str, Any], method: str) -> float:
    return round(_to_float(_settlement_block(doc)["remainder"].get(method), 0.0), 4)


def _set_settlement_remainder(doc: dict[str, Any], method: str, value: float) -> None:
    block = _settlement_block(doc)
    block["remainder"][method] = round(max(0.0, value), 4)
    block["updated_at"] = _now()
    doc["association_settlement"] = block


def _settlement_gift_name(entry: dict[str, Any], method: str) -> str:
    note = _clean(entry.get("note"), 200)
    match = re.match(r"^(.+?)\s*(?:×|x|\*)\s*\d+", note)
    if match:
        name = _clean(match.group(1), 60)
        if name:
            return name
    if method == "鸡腿":
        return "琴音生花"
    return "计分卡"


def _settlement_plan(doc: dict[str, Any], entry_id: str) -> dict[str, Any]:
    """预演“重复条目代投应援会”。

    重复条目的分数（加上该计分方式此前结转的剩余分）按时间从早到晚
    依次覆盖同计分方式的应援会条目；只有能被完整覆盖的条目才会标记已投，
    不足以完整覆盖的下一条目保持原状态，剩余分结转到下一次。
    """
    entries = [item for item in doc.get("entries") or [] if isinstance(item, dict)]
    source = next((item for item in entries if _clean(item.get("id"), 80) == _clean(entry_id, 80)), None)
    if source is None:
        raise ValueError("条目不存在")
    source_name = _clean(source.get("source"), 20)
    if source_name in ASSOCIATION_SOURCES:
        raise ValueError("应援会来源条目不能标记重复")
    if isinstance(source.get("proxy_settlement"), dict) and source.get("proxy_settlement"):
        raise ValueError("该条目已完成代投，不能重复代投")
    method = _entry_scoring_method(source)
    entry_score = round(_to_float(source.get("score"), 0.0), 4)
    gift_name = _settlement_gift_name(source, method)
    pool = _settlement_remainder(doc, method)
    available = round(pool + entry_score, 4)
    candidates = sorted(
        (
            item
            for item in entries
            if _clean(item.get("source"), 20) in ASSOCIATION_SOURCES
            and not item.get("duplicate")
            and _entry_status(item) != "settled"
            and _entry_scoring_method(item) == method
            and _to_float(item.get("score"), 0.0) > 0
        ),
        key=lambda item: (_entry_time(item), _clean(item.get("id"), 80)),
    )
    allocations: list[dict[str, Any]] = []
    next_item: dict[str, Any] | None = None
    for candidate in candidates:
        score = round(_to_float(candidate.get("score"), 0.0), 4)
        if available + 0.0001 < score:
            next_item = {
                "entry_id": _clean(candidate.get("id"), 80),
                "fan_name": _clean(candidate.get("fan_name") or candidate.get("raw_name") or "未登记", 120),
                "source": _clean(candidate.get("source"), 20),
                "source_label": SOURCE_LABELS.get(_clean(candidate.get("source"), 20), ""),
                "source_time": _entry_time(candidate),
                "score": score,
                "shortfall": round(score - available, 4),
            }
            break
        allocations.append(
            {
                "entry_id": _clean(candidate.get("id"), 80),
                "fan_name": _clean(candidate.get("fan_name") or candidate.get("raw_name") or "未登记", 120),
                "source": _clean(candidate.get("source"), 20),
                "source_label": SOURCE_LABELS.get(_clean(candidate.get("source"), 20), ""),
                "source_time": _entry_time(candidate),
                "score": score,
                "covered_score": score,
            }
        )
        available = round(available - score, 4)
    covered_score = round(sum(item["covered_score"] for item in allocations), 4)
    return {
        "entry": {
            "id": _clean(source.get("id"), 80),
            "fan_name": _clean(source.get("fan_name") or source.get("raw_name") or "未登记", 120),
            "raw_name": _clean(source.get("raw_name"), 120),
            "source": source_name,
            "source_label": SOURCE_LABELS.get(source_name, source_name),
            "source_time": _entry_time(source),
            "score": entry_score,
            "scoring_method": method,
            "duplicate": bool(source.get("duplicate")),
        },
        "method": method,
        "gift_name": gift_name,
        "pool_remainder": pool,
        "entry_score": entry_score,
        "available_score": round(pool + entry_score, 4),
        "allocations": allocations,
        "covered_count": len(allocations),
        "covered_score": covered_score,
        "remainder": round(max(0.0, available), 4),
        "next": next_item,
    }


def _mutator_settle_association(doc: dict[str, Any], payload: dict[str, Any]):
    entry_id = _clean(payload.get("entry_id") or payload.get("id"), 80)
    if not entry_id:
        raise ValueError("缺少条目 ID")
    plan = _settlement_plan(doc, entry_id)
    method = plan["method"]
    now = _now()
    covered_ids = {item["entry_id"] for item in plan["allocations"]}
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict) or _clean(entry.get("id"), 80) not in covered_ids:
            continue
        entry["status"] = "settled"
        entry["settled"] = True
        entry["settled_at"] = now
        sources = entry.get("settled_by_duplicates")
        if not isinstance(sources, list):
            sources = []
        if entry_id not in sources:
            sources.append(entry_id)
        entry["settled_by_duplicates"] = sources
        entry["updated_at"] = now
    source = next(
        (item for item in doc.get("entries") or [] if isinstance(item, dict) and _clean(item.get("id"), 80) == entry_id),
        None,
    )
    if source is None:
        raise ValueError("条目不存在")
    source["duplicate"] = True
    source["proxy_settlement"] = {
        "method": method,
        "gift_name": plan["gift_name"],
        "entry_score": plan["entry_score"],
        "pool_before": plan["pool_remainder"],
        "available_score": plan["available_score"],
        "covered": plan["allocations"],
        "covered_score": plan["covered_score"],
        "remainder": plan["remainder"],
        "applied_at": now,
    }
    if not source.get("duplicate_note"):
        source["duplicate_note"] = f"代投应援会·{method}"
    source["updated_at"] = now
    _set_settlement_remainder(doc, method, plan["remainder"])
    return doc, {
        "entry_id": entry_id,
        "method": method,
        "covered_count": plan["covered_count"],
        "covered_score": plan["covered_score"],
        "remainder": plan["remainder"],
        "allocations": plan["allocations"],
    }


def _business_option(value: Any, group: str | None = None) -> str:
    text = _clean(value, 80)
    allowed = BUSINESS_GROUP_VALUES.get(group, BUSINESS_OPTION_VALUES) if group else BUSINESS_OPTION_VALUES
    return text if text in allowed else ""


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _norm_date(value: str) -> str:
    value = _clean(value, 10)
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")


def _valid_job_id(value: str) -> str:
    value = _clean(value, 64)
    if not JOB_ID_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail="无效的任务 ID")
    return value


# ── 微店同步：主节点自动补采 / 副本节点转发 ─────────────────────────────

_WEIDIAN_SYNC_LOCK = threading.Lock()
_WEIDIAN_AUTO_SYNC_STARTED = False
_WEIDIAN_AUTO_SYNC_LOCK_FILE: Any = None


def _primary() -> bool:
    return bool(cfg.SHARED_STATE_IS_PRIMARY or not cfg.SHARED_STATE_SYNC_ENABLED)


def _parse_bj_time(value: Any) -> datetime | None:
    text = _clean(value, 32)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BJ_TZ)
    except ValueError:
        return None


def _weidian_sync_state_path() -> Path:
    return Path(cfg.REDBLUE_WEIDIAN_SYNC_STATE_PATH)


def _load_weidian_sync_state() -> dict[str, Any]:
    data = _load_json(_weidian_sync_state_path())
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", 1)
    data.setdefault("status", "unknown")
    data.setdefault("last_success_at", "")
    data.setdefault("last_attempt_at", "")
    data.setdefault("last_job_id", "")
    data.setdefault("last_error", "")
    data.setdefault("generated_at", "")
    data.setdefault("orders_count", 0)
    data.setdefault("created", 0)
    data.setdefault("updated", 0)
    data.setdefault("skipped", False)
    return data


def _save_weidian_sync_state(data: dict[str, Any]) -> None:
    path = _weidian_sync_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, 0o664)
    except OSError:
        pass
    os.replace(temporary, path)


def _weidian_sync_status() -> dict[str, Any]:
    state = _load_weidian_sync_state()
    state["interval_seconds"] = int(cfg.REDBLUE_WEIDIAN_AUTO_SYNC_INTERVAL_SECONDS)
    state["is_primary"] = _primary()
    if not _primary():
        state["status"] = "replica"
        state["note"] = "微店同步由腾讯云主节点自动执行，阿里云使用共享台账副本"
        state["stale"] = False
        return state
    last_success = _parse_bj_time(state.get("last_success_at"))
    if last_success is None:
        state["stale"] = True
        state["stale_seconds"] = None
    else:
        stale_seconds = int((datetime.now(BJ_TZ) - last_success).total_seconds())
        state["stale_seconds"] = max(0, stale_seconds)
        state["stale"] = stale_seconds > max(60, int(cfg.REDBLUE_WEIDIAN_AUTO_SYNC_INTERVAL_SECONDS) * 2)
    return state


_INTERNAL_ERROR_MARKERS = (
    "ssh",
    "connect to host",
    "connection",
    "timed out",
    "timeout",
    "socket",
    "traceback",
    "shared-state peer",
    "peer_command",
    "subprocess",
    "/home/",
    "scp",
    "rsync",
)


def _public_detail(exc: Exception | str, fallback: str) -> str:
    """Hide infrastructure details (SSH paths/hosts, tracebacks) from the page."""
    text = str(exc or "").strip()
    lowered = text.lower()
    if not text or any(marker in lowered for marker in _INTERNAL_ERROR_MARKERS):
        logger.warning("redblue internal error hidden from client: %s", text[:500])
        return fallback
    return text


def _peer_weidian(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = peer_command("weidian-admin", {"action": action, "payload": payload})
    except SharedStatePeerError as exc:
        logger.warning("redblue weidian peer failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="主节点暂时不可用，请稍后重试",
        ) from exc
    if not isinstance(response, dict):
        raise HTTPException(status_code=502, detail="服务暂时不可用，请稍后重试")
    response.pop("ok", None)
    return response


def _pending_weidian_sync_job() -> str:
    """复用队列里尚未完成的 sync 任务，避免 worker 停摆时堆积重复任务。"""
    try:
        _, pending, _, _ = _queue_dirs("weidian")
    except OSError:
        return ""
    target = Path(cfg.REDBLUE_WEIDIAN_ORDERS_PATH).resolve()
    for path in sorted(pending.glob("*.json")):
        data = _load_json(path)
        if not isinstance(data, dict) or _clean(data.get("type"), 20) != "sync":
            continue
        output = _clean(data.get("output_path"), 500)
        try:
            output_path = Path(output).resolve() if output else target
        except (OSError, ValueError):
            output_path = target
        if output_path != target:
            continue
        return path.stem
    return ""


def _apply_weidian_orders(orders: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        doc = load_document(RESOURCE)
    except SharedStateError:
        doc = {}
    if not _weidian_changed(doc, orders):
        return {"created": 0, "updated": 0, "skipped": True}
    result = execute_mutation(
        RESOURCE,
        "upsert_weidian",
        {"orders": orders},
        operation_id=uuid.uuid4().hex,
    )
    return result.get("result") or {}


def _record_weidian_job_result(result: dict[str, Any], job_id: str) -> None:
    """手动同步只更新“最近尝试”；成功入库仍以 apply 为准。"""
    if not _primary():
        return
    state = _load_weidian_sync_state()
    status = _clean(result.get("status"), 20)
    if status == "error":
        state["status"] = "error"
        state["last_error"] = _clean(result.get("error"), 300) or "微店同步失败"
        state["last_attempt_at"] = _now()
        state["last_job_id"] = job_id
        _save_weidian_sync_state(state)
    elif status == "done":
        state["status"] = "running"
        state["last_attempt_at"] = state.get("last_attempt_at") or _now()
        state["last_job_id"] = job_id
        _save_weidian_sync_state(state)


def _mark_weidian_sync_applied(data: dict[str, Any], applied: dict[str, Any]) -> None:
    if not _primary():
        return
    state = _load_weidian_sync_state()
    orders = data.get("orders") if isinstance(data.get("orders"), list) else []
    state.update(
        {
            "status": "ok",
            "last_success_at": _now(),
            "last_error": "",
            "generated_at": _clean(data.get("generated_at"), 32),
            "orders_count": len(orders),
            "created": int(applied.get("created", 0) or 0),
            "updated": int(applied.get("updated", 0) or 0),
            "skipped": bool(applied.get("skipped")),
        }
    )
    _save_weidian_sync_state(state)


def run_weidian_sync_once(*, force: bool = False) -> dict[str, Any]:
    """执行一轮同步并入库；失败时保留状态供自动重试。"""
    if not _WEIDIAN_SYNC_LOCK.acquire(timeout=5):
        return {"status": "busy", "note": "已有微店同步在进行"}
    try:
        state = _load_weidian_sync_state()
        last_success = _parse_bj_time(state.get("last_success_at"))
        if not force and last_success is not None:
            elapsed = (datetime.now(BJ_TZ) - last_success).total_seconds()
            if elapsed < max(60, int(cfg.REDBLUE_WEIDIAN_AUTO_SYNC_INTERVAL_SECONDS)):
                return {"status": "skipped", "reason": "fresh", "elapsed_seconds": int(elapsed)}
        payload = {
            "type": "sync",
            "item_id": cfg.REDBLUE_WEIDIAN_ITEM_ID,
            "item_ids": list(cfg.REDBLUE_WEIDIAN_ITEM_IDS),
            "output_path": cfg.REDBLUE_WEIDIAN_ORDERS_PATH,
        }
        job_id = _pending_weidian_sync_job() or _write_job("weidian", payload)
        state.update(
            {
                "status": "running",
                "last_attempt_at": _now(),
                "last_job_id": job_id,
                "last_error": "",
            }
        )
        _save_weidian_sync_state(state)

        deadline = time.time() + max(30, int(cfg.REDBLUE_WEIDIAN_SYNC_JOB_TIMEOUT_SECONDS))
        result: dict[str, Any] = {"status": "pending"}
        while time.time() < deadline:
            result = _read_job_result("weidian", job_id)
            if _clean(result.get("status"), 20) in {"done", "error", "missing"}:
                break
            time.sleep(2)

        status = _clean(result.get("status"), 20)
        if status == "done":
            data = _load_json(Path(cfg.REDBLUE_WEIDIAN_ORDERS_PATH))
            orders = data.get("orders") if isinstance(data, dict) and isinstance(data.get("orders"), list) else []
            if not orders:
                state.update({"status": "error", "last_error": "微店订单文件为空"})
                _save_weidian_sync_state(state)
                return {"status": "error", "error": "微店订单文件为空", "job_id": job_id}
            applied = _apply_weidian_orders(orders)
            _mark_weidian_sync_applied(data, applied)
            return {"status": "ok", "job_id": job_id, "orders_count": len(orders), **applied}
        error = _clean(result.get("error"), 300) or (
            "微店同步任务超时" if status == "pending" else "微店同步任务结果缺失"
        )
        state.update({"status": "error", "last_error": error})
        _save_weidian_sync_state(state)
        return {"status": "error", "error": error, "job_id": job_id}
    finally:
        _WEIDIAN_SYNC_LOCK.release()


def _weidian_auto_sync_loop() -> None:
    time.sleep(15)
    while True:
        try:
            state = _load_weidian_sync_state()
            last_success = _parse_bj_time(state.get("last_success_at"))
            last_attempt = _parse_bj_time(state.get("last_attempt_at"))
            now = datetime.now(BJ_TZ)
            retrying = _clean(state.get("status"), 20) == "error"
            wait_seconds = int(
                cfg.REDBLUE_WEIDIAN_AUTO_SYNC_RETRY_SECONDS
                if retrying
                else cfg.REDBLUE_WEIDIAN_AUTO_SYNC_INTERVAL_SECONDS
            )
            anchor = max(
                [value for value in (last_success, last_attempt) if value is not None],
                default=None,
            )
            if anchor is None or (now - anchor).total_seconds() >= max(30, wait_seconds):
                result = run_weidian_sync_once(force=True)
                logger.info(
                    "weidian auto sync: %s%s",
                    result.get("status"),
                    f" ({result.get('error')})" if result.get("error") else "",
                )
        except Exception:  # noqa: BLE001
            logger.exception("weidian auto sync loop failed")
        time.sleep(30)


def start_weidian_auto_sync() -> None:
    """启动主节点的微店自动同步循环；只允许一个进程持有锁。"""
    global _WEIDIAN_AUTO_SYNC_STARTED, _WEIDIAN_AUTO_SYNC_LOCK_FILE
    if _WEIDIAN_AUTO_SYNC_STARTED:
        return
    if not cfg.REDBLUE_WEIDIAN_AUTO_SYNC_ENABLED or not _primary():
        return
    lock_path = _weidian_sync_state_path().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return
    _WEIDIAN_AUTO_SYNC_LOCK_FILE = handle
    _WEIDIAN_AUTO_SYNC_STARTED = True
    threading.Thread(
        target=_weidian_auto_sync_loop,
        name="redblue-weidian-auto-sync",
        daemon=True,
    ).start()


# ── 鉴权 ────────────────────────────────────────────────────────────────


def verify_redblue_password(
    request: Request,
    x_redblue_password: str = Header(None, alias="X-Redblue-Password"),
    redblue_ledger_auth: str = Cookie(None, alias=AUTH_COOKIE),
):
    expected = cfg.REDBLUE_LEDGER_PASSWORD
    if not expected:
        raise HTTPException(status_code=403, detail="红蓝计分台账页未启用")
    if redblue_ledger_auth and hmac.compare_digest(
        redblue_ledger_auth, _cookie_token(expected)
    ):
        return True
    if x_redblue_password and hmac.compare_digest(x_redblue_password, expected):
        return True
    if not password_session.password_was_submitted(x_redblue_password):
        # 缺密码或旧 Cookie 一律视为“登录已过期”，不计入密码失败限流。
        raise HTTPException(status_code=401, detail="需要密码")
    check_redblue_login_limit(request)
    raise HTTPException(status_code=403, detail="密码错误")


def check_redblue_login_limit(request: Request) -> None:
    _check_redblue_login_limit(
        get_client_ip(request), "红蓝台账密码尝试过于频繁，请稍后再试"
    )


@router.post("/login")
def login(payload: LoginRequest, response: Response, request: Request):
    expected = cfg.REDBLUE_LEDGER_PASSWORD
    if not expected:
        raise HTTPException(status_code=403, detail="红蓝计分台账页未启用")
    if not hmac.compare_digest(payload.password, expected):
        check_redblue_login_limit(request)
        raise HTTPException(status_code=403, detail="密码错误")
    response.set_cookie(
        key=AUTH_COOKIE,
        value=_cookie_token(expected),
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
        path="/api/redblue",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=AUTH_COOKIE,
        path="/api/redblue",
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}


@router.get("/verify")
def verify_redblue_login(response: Response, _=Depends(verify_redblue_password)):
    response.headers["Cache-Control"] = "no-store"
    return {"verified": True}


# ── 身份索引 ────────────────────────────────────────────────────────────

_IDENTITY_LOCK = threading.Lock()
_ROOM_LIVE_SYNC_LOCK = threading.Lock()
_IDENTITY_CACHE: dict[str, Any] = {"signature": None, "index": None}


def _empty_identity() -> dict[str, Any]:
    return {"by_id": {}, "by_name": {}, "generated_at": "", "sources": []}


def _add_identity(index: dict[str, Any], fan_id: str, name: str, seen: str = "") -> None:
    fan_id = _clean(fan_id, 32)
    name = _clean(name, 120)
    if not fan_id and not name:
        return
    if fan_id:
        account = index["by_id"].setdefault(
            fan_id,
            {"fan_id": fan_id, "names": set(), "latest_name": "", "last_seen": ""},
        )
        if name:
            account["names"].add(name)
            if not seen or seen >= str(account.get("last_seen") or ""):
                account["latest_name"] = name
                account["last_seen"] = seen or account.get("last_seen") or ""
    if name:
        nick = index["by_name"].setdefault(
            name,
            {"name": name, "ids": set(), "last_seen": ""},
        )
        if fan_id:
            nick["ids"].add(fan_id)
        if seen and seen >= str(nick.get("last_seen") or ""):
            nick["last_seen"] = seen


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fallback_identity_signature() -> tuple[Any, ...]:
    paths: list[Path] = []
    for key in ("sender_identity_map", "sender_profiles", "fan_name_map"):
        value = (cfg.REDBLUE_IDENTITY_FALLBACK_PATHS or {}).get(key)
        if value:
            paths.append(Path(value))
    signature: list[Any] = []
    for path in paths:
        try:
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(path), 0, 0))
    return tuple(signature)


def _merge_sender_identity(index: dict[str, Any], data: dict[str, Any]) -> None:
    for item in data.get("nicknames") or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("sender_name"), 120)
        ids = item.get("sender_ids") if isinstance(item.get("sender_ids"), list) else []
        if not ids and item.get("sender_id"):
            ids = [item.get("sender_id")]
        seen = _clean(item.get("latest_seen"), 32)
        for fan_id in ids:
            _add_identity(index, str(fan_id), name, seen)
        if not ids and name:
            _add_identity(index, "", name, seen)
    for item in data.get("accounts") or []:
        if not isinstance(item, dict):
            continue
        fan_id = _clean(item.get("sender_id"), 32)
        latest = _clean(item.get("latest_sender_name"), 120)
        seen = _clean(item.get("latest_seen"), 32)
        if latest:
            _add_identity(index, fan_id, latest, seen)
        for name in item.get("sender_names") or []:
            _add_identity(index, fan_id, str(name), seen)


def _merge_profiles(index: dict[str, Any], data: dict[str, Any]) -> None:
    profiles = data.get("profile_data")
    if not isinstance(profiles, dict):
        return
    for fan_id, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        name = _clean(profile.get("nickName"), 120)
        if name:
            _add_identity(index, str(fan_id), name)


def _merge_name_map(index: dict[str, Any], data: dict[str, Any]) -> None:
    mapping = data.get("map")
    if not isinstance(mapping, dict):
        return
    for raw_name, item in mapping.items():
        if not isinstance(item, dict):
            continue
        fan_id = _clean(item.get("uid"), 32)
        latest = _clean(item.get("latest") or raw_name, 120)
        seen = _clean(item.get("last_seen"), 32)
        _add_identity(index, fan_id, latest, seen)
        if fan_id and raw_name != latest:
            _add_identity(index, fan_id, str(raw_name), seen)


def _load_identity_base() -> dict[str, Any]:
    shared = identity_index.redblue_index()
    if shared["by_id"] or shared["by_name"]:
        return shared

    # Legacy deployments only have the fallback files.  Their signature is
    # intentionally separate so frequent fallback rewrites cannot invalidate
    # the primary index cache.
    signature = _fallback_identity_signature()
    with _IDENTITY_LOCK:
        if _IDENTITY_CACHE.get("signature") == signature and isinstance(_IDENTITY_CACHE.get("index"), dict):
            return _IDENTITY_CACHE["index"]
        index = _empty_identity()
        sender_map = _load_json(Path((cfg.REDBLUE_IDENTITY_FALLBACK_PATHS or {}).get("sender_identity_map", "")))
        if isinstance(sender_map, dict):
            _merge_sender_identity(index, sender_map)
        profiles = _load_json(Path((cfg.REDBLUE_IDENTITY_FALLBACK_PATHS or {}).get("sender_profiles", "")))
        if isinstance(profiles, dict):
            _merge_profiles(index, profiles)
        name_map = _load_json(Path((cfg.REDBLUE_IDENTITY_FALLBACK_PATHS or {}).get("fan_name_map", "")))
        if isinstance(name_map, dict):
            _merge_name_map(index, name_map)
        _IDENTITY_CACHE["signature"] = signature
        _IDENTITY_CACHE["index"] = index
        return index


def _alias_maps(aliases: Iterable[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_name: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for alias in aliases:
        if not isinstance(alias, dict):
            continue
        name = _clean(alias.get("raw_name"), 120)
        fan_id = _clean(alias.get("fan_id"), 32)
        fan_name = _clean(alias.get("fan_name"), 120)
        if not fan_id:
            continue
        record = {"fan_id": fan_id, "fan_name": fan_name}
        if name:
            by_name[name] = record
        by_id[fan_id] = record
    return by_name, by_id


def _resolve_identity(
    raw_name: str,
    raw_id: str,
    aliases: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    raw_name = _clean(raw_name, 120)
    raw_id = _clean(raw_id, 32)
    alias_by_name, alias_by_id = _alias_maps(aliases)
    if raw_id:
        account = _load_identity_base()["by_id"].get(raw_id)
        if account:
            return {
                "fan_id": raw_id,
                "fan_name": account.get("latest_name") or raw_name,
                "warning": False,
                "reason": "",
            }
        alias = alias_by_id.get(raw_id)
        if alias:
            return {"fan_id": raw_id, "fan_name": alias.get("fan_name") or raw_name, "warning": False, "reason": ""}
        return {"fan_id": "", "fan_name": raw_name, "warning": True, "reason": "口袋48 ID 未找到"}
    if raw_name:
        if raw_name.isdigit():
            account = _load_identity_base()["by_id"].get(raw_name)
            if account:
                return {
                    "fan_id": raw_name,
                    "fan_name": account.get("latest_name") or raw_name,
                    "warning": False,
                    "reason": "",
                }
        nick = _load_identity_base()["by_name"].get(raw_name)
        if nick:
            ids = sorted(str(item) for item in (nick.get("ids") or []))
            if len(ids) == 1:
                account = _load_identity_base()["by_id"].get(ids[0], {})
                return {
                    "fan_id": ids[0],
                    "fan_name": account.get("latest_name") or raw_name,
                    "warning": False,
                    "reason": "",
                }
            if len(ids) > 1:
                alias = alias_by_name.get(raw_name)
                if alias:
                    return {
                        "fan_id": alias["fan_id"],
                        "fan_name": alias.get("fan_name") or raw_name,
                        "warning": False,
                        "reason": "",
                    }
                return {
                    "fan_id": "",
                    "fan_name": raw_name,
                    "warning": True,
                    "reason": f"昵称对应多个口袋48账号：{', '.join(ids[:5])}",
                }
        alias = alias_by_name.get(raw_name)
        if alias:
            return {
                "fan_id": alias["fan_id"],
                "fan_name": alias.get("fan_name") or raw_name,
                "warning": False,
                "reason": "",
            }
        return {"fan_id": "", "fan_name": raw_name, "warning": True, "reason": "未找到该口袋48昵称"}
    return {"fan_id": "", "fan_name": "", "warning": True, "reason": "缺少口袋48昵称或 ID"}


# ── 条目工具 ────────────────────────────────────────────────────────────


def _entry_time(item: dict[str, Any]) -> str:
    return _clean(item.get("source_time") or item.get("created_at"), 32)


def _entry_key(item: dict[str, Any]) -> str:
    fan_id = _clean(item.get("fan_id"), 32)
    if fan_id:
        return f"id:{fan_id}"
    return f"name:{_clean(item.get('fan_name') or item.get('raw_name'), 120)}"


def _business_name(value: Any) -> str:
    text = _clean(value, 80)
    option = BUSINESS_OPTION_MAP.get(text)
    if option:
        return str(option["name"])
    return re.sub(r"^\d+(?:\.\d+)?-", "", text)


def _entry_fan_key(entry: dict[str, Any]) -> str:
    return _fan_business_key(entry.get("fan_id"), entry.get("fan_name") or entry.get("raw_name"))


def _entry_fan_name(entry: dict[str, Any]) -> str:
    return _clean(entry.get("fan_name") or entry.get("raw_name"), 120)


def _redemption_participants(
    allocations: Iterable[dict[str, Any]],
    entries_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in allocations:
        entry = entries_by_id.get(_clean(row.get("entry_id"), 80)) or {}
        key = _entry_fan_key(entry)
        if not key:
            continue
        participant = rows.setdefault(
            key,
            {
                "fan_id": _clean(entry.get("fan_id"), 32),
                "fan_name": _entry_fan_name(entry),
                "score": 0.0,
                "entry_count": 0,
                "_first_time": str(row.get("entry_time") or ""),
            },
        )
        participant["score"] = round(participant["score"] + _to_float(row.get("score"), 0.0), 4)
        participant["entry_count"] += 1
        row_time = str(row.get("entry_time") or "")
        if row_time and (not participant["_first_time"] or row_time < participant["_first_time"]):
            participant["_first_time"] = row_time
    result = sorted(
        rows.values(),
        key=lambda item: (str(item.get("_first_time") or ""), item["fan_id"], item["fan_name"]),
    )
    for item in result:
        item.pop("_first_time", None)
    return result


def _redemption_status(value: Any) -> str:
    return "done" if _clean(value, 20).lower() in {"done", "complete", "completed", "finished", "已完成"} else "pending"


def _redemption_allocations_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("allocations")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry_id = _clean(row.get("entry_id"), 80)
        amount = _to_float(row.get("score"), 0.0)
        if not entry_id or amount <= 0:
            continue
        if entry_id in seen:
            raise ValueError("同一条目不能重复分摊")
        seen.add(entry_id)
        result.append({"entry_id": entry_id, "score": round(amount, 4)})
    return result


def _entry_used_scores(redemptions: Iterable[dict[str, Any]], exclude_id: str = "") -> dict[str, float]:
    used: dict[str, float] = {}
    exclude_id = _clean(exclude_id, 80)
    for redemption in redemptions:
        if not isinstance(redemption, dict) or _clean(redemption.get("id"), 80) == exclude_id:
            continue
        allocations = redemption.get("allocations") if isinstance(redemption.get("allocations"), list) else []
        for row in allocations:
            if not isinstance(row, dict):
                continue
            entry_id = _clean(row.get("entry_id"), 80)
            if entry_id:
                used[entry_id] = round(used.get(entry_id, 0.0) + _to_float(row.get("score"), 0.0), 4)
    return used


def _auto_allocate_redemption(
    entries: Iterable[dict[str, Any]],
    used: dict[str, float],
    cost: float,
    scoring_method: str,
) -> list[dict[str, Any]]:
    remaining = round(cost, 4)
    allocations: list[dict[str, Any]] = []
    candidates = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and not entry.get("duplicate")
        and _entry_scoring_method(entry) == scoring_method
        and _to_float(entry.get("score"), 0.0) > 0
    ]
    for entry in sorted(candidates, key=lambda item: (_entry_time(item), _clean(item.get("id"), 80))):
        entry_id = _clean(entry.get("id"), 80)
        if not entry_id:
            continue
        available = round(_to_float(entry.get("score"), 0.0) - used.get(entry_id, 0.0), 4)
        if available <= 0:
            continue
        amount = round(min(available, remaining), 4)
        allocations.append({"entry_id": entry_id, "score": amount})
        remaining = round(remaining - amount, 4)
        if remaining <= 0.0001:
            break
    if remaining > 0.0001:
        raise ValueError("所选粉丝剩余可兑换分数不足")
    return allocations


def _completion_entry_id(
    allocations: list[dict[str, Any]],
    entries_by_id: dict[str, dict[str, Any]],
    cost: float,
) -> str:
    ordered = []
    for row in allocations:
        entry = entries_by_id.get(row["entry_id"])
        if entry is None:
            continue
        ordered.append((_entry_time(entry), row["entry_id"], _to_float(row.get("score"), 0.0)))
    ordered.sort()
    total = 0.0
    for _time, entry_id, amount in ordered:
        total = round(total + amount, 4)
        if total >= cost - 0.0001:
            return entry_id
    return ordered[-1][1] if ordered else ""


def _normalise_redemption(raw: dict[str, Any], entries_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    business = _clean(raw.get("business"), 80)
    option = BUSINESS_OPTION_MAP.get(business)
    allocations = []
    for row in raw.get("allocations") if isinstance(raw.get("allocations"), list) else []:
        if not isinstance(row, dict):
            continue
        entry_id = _clean(row.get("entry_id"), 80)
        amount = _to_float(row.get("score"), 0.0)
        if not entry_id or amount <= 0:
            continue
        entry = entries_by_id.get(entry_id) or {}
        allocations.append({
            "entry_id": entry_id,
            "score": round(amount, 4),
            "entry_time": _entry_time(entry),
            "entry_source": _clean(entry.get("source"), 20),
            "fan_id": _clean(entry.get("fan_id"), 32),
            "fan_name": _entry_fan_name(entry),
        })
    allocations.sort(key=lambda item: (item.get("entry_time") or "", item["entry_id"]))
    display_entry_id = _clean(allocations[0]["entry_id"], 80) if allocations else ""
    display_entry = entries_by_id.get(display_entry_id) or {}
    cost = round(_to_float(raw.get("cost"), _to_float(option["score"] if option else 0.0, 0.0)), 4)
    methods = {
        _entry_scoring_method(entries_by_id[row["entry_id"]])
        for row in allocations
        if entries_by_id.get(row["entry_id"])
    }
    derived_method = next(iter(methods)) if len(methods) == 1 else ""
    raw_method = _clean(raw.get("scoring_method"), 10)
    scoring_method = raw_method if raw_method in SCORING_METHODS else derived_method
    bonus_business = _clean(raw.get("bonus_business"), 80)
    bonus_option = BONUS_OPTION_MAP.get(bonus_business) if bonus_business else None
    if bonus_option is None:
        bonus_business = ""
    completion_entry_id = _completion_entry_id(allocations, entries_by_id, cost)
    completion_entry = entries_by_id.get(completion_entry_id) or {}
    participants = _redemption_participants(allocations, entries_by_id)
    fan_id = _clean(raw.get("fan_id"), 32)
    fan_name = _clean(raw.get("fan_name"), 120)
    if not fan_id and not fan_name:
        fan_id = _clean(completion_entry.get("fan_id"), 32)
        fan_name = _entry_fan_name(completion_entry)
    if not fan_name and allocations:
        first = entries_by_id.get(allocations[0]["entry_id"]) or {}
        fan_id = fan_id or _clean(first.get("fan_id"), 32)
        fan_name = _entry_fan_name(first)
    if not fan_name and participants:
        fan_id = fan_id or participants[0]["fan_id"]
        fan_name = participants[0]["fan_name"]
    status = _redemption_status(raw.get("status"))
    return {
        "id": _clean(raw.get("id"), 80),
        "fan_id": fan_id,
        "fan_name": fan_name,
        "participants": participants,
        "business": business,
        "business_name": str(option["name"]) if option else _business_name(business),
        "bonus_business": bonus_business,
        "bonus_business_name": str(bonus_option["name"]) if bonus_option else "",
        "scoring_method": scoring_method,
        "group": _clean(raw.get("group") or (option["group"] if option else ""), 20),
        "cost": cost,
        "status": status,
        "note": _clean(raw.get("note")),
        "allocations": allocations,
        "display_entry_id": display_entry_id,
        "display_entry_time": _entry_time(display_entry),
        "completion_entry_id": completion_entry_id,
        "completion_entry_time": _entry_time(completion_entry),
        "created_at": _clean(raw.get("created_at"), 32),
        "updated_at": _clean(raw.get("updated_at"), 32),
        "completed_at": _clean(raw.get("completed_at"), 32),
    }


def _normalise_redemptions(raw_redemptions: Iterable[dict[str, Any]], all_entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    entries_by_id = {
        _clean(entry.get("id"), 80): entry
        for entry in all_entries
        if isinstance(entry, dict) and _clean(entry.get("id"), 80)
    }
    result = [
        _normalise_redemption(item, entries_by_id)
        for item in raw_redemptions
        if isinstance(item, dict) and _clean(item.get("id"), 80)
    ]
    return sorted(result, key=lambda item: (item.get("created_at") or "", item["id"]))


def _attach_business_allocations(entries: Iterable[dict[str, Any]], redemptions: list[dict[str, Any]]) -> None:
    allocations_by_entry: dict[str, list[dict[str, Any]]] = {}
    display_labels_by_entry: dict[str, list[str]] = {}
    for redemption in redemptions:
        completion_id = _clean(redemption.get("completion_entry_id"), 80)
        allocations = redemption.get("allocations") or []
        display_id = _clean(redemption.get("display_entry_id"), 80)
        if not display_id and allocations:
            display_id = _clean(allocations[0].get("entry_id"), 80)
        for row in allocations:
            entry_id = _clean(row.get("entry_id"), 80)
            if not entry_id:
                continue
            allocations_by_entry.setdefault(entry_id, []).append({
                "redemption_id": redemption["id"],
                "business": redemption["business"],
                "business_name": redemption["business_name"],
                "bonus_business": redemption.get("bonus_business") or "",
                "bonus_business_name": redemption.get("bonus_business_name") or "",
                "group": redemption["group"],
                "cost": redemption["cost"],
                "score": row["score"],
                "fan_id": row.get("fan_id") or "",
                "fan_name": row.get("fan_name") or "",
                "status": redemption["status"],
                "completion": entry_id == completion_id,
                "participants": redemption.get("participants") or [],
            })
        if display_id:
            display_labels_by_entry.setdefault(display_id, []).append(redemption["business_name"])
            if redemption.get("bonus_business_name"):
                display_labels_by_entry.setdefault(display_id, []).append(redemption["bonus_business_name"])
    for entry in entries:
        entry_id = _clean(entry.get("id"), 80)
        allocations = allocations_by_entry.get(entry_id, [])
        allocated = round(sum(_to_float(item.get("score"), 0.0) for item in allocations), 4)
        entry["business_allocations"] = allocations
        entry["business_allocated_score"] = allocated
        entry["business_remaining_score"] = round(max(0.0, _to_float(entry.get("score"), 0.0) - allocated), 4)
        entry["business_display_labels"] = display_labels_by_entry.get(entry_id, [])
        statuses = [item.get("status") for item in allocations]
        entry["business_status"] = (
            "done" if statuses and all(item == "done" for item in statuses) else
            "pending" if statuses else ""
        )


def _fan_business_key(fan_id: Any, fan_name: Any) -> str:
    fan_id = _clean(fan_id, 32)
    if fan_id:
        return f"id:{fan_id}"
    fan_name = _clean(fan_name, 120)
    return f"name:{fan_name}" if fan_name else ""


def _attach_fan_business(fan_summary: Iterable[dict[str, Any]], redemptions: list[dict[str, Any]]) -> None:
    by_fan: dict[str, list[dict[str, Any]]] = {}
    for redemption in redemptions:
        owner_key = _fan_business_key(redemption.get("fan_id"), redemption.get("fan_name"))
        shares: dict[str, dict[str, Any]] = {}
        for row in redemption.get("allocations") or []:
            key = _fan_business_key(row.get("fan_id"), row.get("fan_name"))
            if not key:
                continue
            share = shares.setdefault(key, {"score": 0.0, "entry_count": 0})
            share["score"] = round(share["score"] + _to_float(row.get("score"), 0.0), 4)
            share["entry_count"] += 1
        if not shares and owner_key:
            shares[owner_key] = {"score": round(_to_float(redemption.get("cost"), 0.0), 4), "entry_count": 1}
        for key, share in shares.items():
            by_fan.setdefault(key, []).append(
                {"redemption": redemption, "share": share["score"], "is_owner": key == owner_key}
            )
    for fan in fan_summary:
        key = _fan_business_key(fan.get("fan_id"), fan.get("fan_name"))
        rows = by_fan.get(key, [])
        allocated = round(sum(_to_float(item.get("share"), 0.0) for item in rows), 4)
        names: list[str] = []
        bonus_names: list[str] = []
        shared_names: list[str] = []
        for item in rows:
            redemption = item["redemption"]
            name = _clean(redemption.get("business_name"), 80)
            bonus_name = _clean(redemption.get("bonus_business_name"), 80)
            if item["is_owner"]:
                if name and name not in names:
                    names.append(name)
                if bonus_name and bonus_name not in bonus_names:
                    bonus_names.append(bonus_name)
            elif name and name not in shared_names:
                shared_names.append(name)
        fan["business_redemptions"] = [
            {
                "id": item["redemption"]["id"],
                "business": item["redemption"]["business"],
                "business_name": item["redemption"]["business_name"],
                "bonus_business": item["redemption"].get("bonus_business") or "",
                "bonus_business_name": item["redemption"].get("bonus_business_name") or "",
                "cost": item["redemption"]["cost"],
                "share_score": item["share"],
                "is_owner": item["is_owner"],
                "status": item["redemption"]["status"],
            }
            for item in rows
        ]
        fan["business_allocated_score"] = allocated
        fan["business_remaining_score"] = round(max(0.0, _to_float(fan.get("total_score"), 0.0) - allocated), 4)
        fan["business_labels"] = names
        fan["business_bonus_labels"] = bonus_names
        fan["business_shared_labels"] = shared_names
        fan["business_status"] = (
            "done" if rows and all(item["redemption"].get("status") == "done" for item in rows) else
            "pending" if rows else ""
        )


def _add_alias(doc: dict[str, Any], raw_name: str, fan_id: str, fan_name: str, source: str) -> None:
    raw_name = _clean(raw_name, 120)
    fan_id = _clean(fan_id, 32)
    if not raw_name or not fan_id:
        return
    aliases = doc.setdefault("aliases", [])
    for alias in aliases:
        if not isinstance(alias, dict):
            continue
        if _clean(alias.get("raw_name"), 120) == raw_name and _clean(alias.get("fan_id"), 32) == fan_id:
            alias["fan_name"] = fan_name
            alias["source"] = source
            alias["updated_at"] = _now()
            return
    aliases.append(
        {
            "raw_name": raw_name,
            "fan_id": fan_id,
            "fan_name": fan_name,
            "source": source,
            "created_at": _now(),
            "updated_at": _now(),
        }
    )


def _apply_identity(
    doc: dict[str, Any],
    entry: dict[str, Any],
    raw_name: str,
    raw_id: str,
    *,
    source: str,
    write_alias: bool = True,
) -> None:
    resolved = _resolve_identity(raw_name, raw_id, doc.get("aliases") or [])
    entry["raw_name"] = raw_name
    entry["raw_id"] = raw_id
    entry["fan_id"] = resolved["fan_id"]
    entry["fan_name"] = resolved["fan_name"] or raw_name
    entry["warning"] = bool(resolved["warning"])
    entry["warning_reason"] = resolved["reason"]
    if write_alias and not resolved["warning"] and resolved["fan_id"]:
        _add_alias(doc, raw_name or resolved["fan_name"], resolved["fan_id"], resolved["fan_name"], source)


def _name_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


_GIFT_PRICE_LOCK = threading.Lock()
_GIFT_PRICE_CACHE: dict[str, Any] = {}


def _gift_price_index() -> tuple[dict[str, float], dict[str, float]]:
    path = Path(getattr(cfg, "REDBLUE_GIFT_AUTHORITY_PATH", "") or "")
    try:
        stat = path.stat()
    except OSError:
        return {}, {}
    signature = (str(path), stat.st_mtime_ns, stat.st_size)
    with _GIFT_PRICE_LOCK:
        if _GIFT_PRICE_CACHE.get("signature") == signature:
            return _GIFT_PRICE_CACHE["by_id"], _GIFT_PRICE_CACHE["by_name"]
        data = _load_json(path)
        by_id: dict[str, float] = {}
        by_name: dict[str, float] = {}
        gifts = data.get("gifts") if isinstance(data, dict) else None
        for gift in gifts or []:
            if not isinstance(gift, dict):
                continue
            price = max(_to_float(gift.get("melee"), 0.0), _to_float(gift.get("money"), 0.0))
            if price <= 0:
                continue
            gift_id = _clean(gift.get("gift_id"), 40)
            gift_name = _clean(gift.get("gift_name"), 160)
            if gift_id:
                by_id[gift_id] = price
            if gift_name:
                by_name[gift_name] = price
        _GIFT_PRICE_CACHE["signature"] = signature
        _GIFT_PRICE_CACHE["by_id"] = by_id
        _GIFT_PRICE_CACHE["by_name"] = by_name
        return by_id, by_name


def _gift_price(gift_name: str, gift_id: str) -> float:
    by_id, by_name = _gift_price_index()
    if gift_id and gift_id in by_id:
        return by_id[gift_id]
    return by_name.get(_clean(gift_name, 160), 0.0)


def _is_chicken_gift(gift_name: str, gift_id: str = "") -> bool:
    """判据：unit_score>0 的计分礼物中，礼物目录有鸡腿价（melee/money>0）即鸡腿。

    不按发送时间判断：计分卡和鸡腿礼物在 11/11–15 可以共存，价格本身是
    礼物的属性；同一 gift_id 只要在 gift.list/目录里带鸡腿价，就是鸡腿礼物。
    """
    gift_id = _clean(gift_id, 40)
    if gift_id and gift_id in _name_set(getattr(cfg, "REDBLUE_CHICKEN_GIFT_IDS", "")):
        return True
    name = _clean(gift_name, 160)
    if not name:
        return False
    if name in _name_set(getattr(cfg, "REDBLUE_CHICKEN_GIFT_NAMES", "")):
        return True
    keywords = _name_set(getattr(cfg, "REDBLUE_CHICKEN_GIFT_KEYWORDS", "鸡腿"))
    if any(keyword in name for keyword in keywords):
        return True
    return _gift_price(name, gift_id) > 0


def _gift_scoring_method(gift_name: str, source: str, gift_id: str = "") -> str:
    if _is_chicken_gift(gift_name, gift_id):
        return "鸡腿"
    return DEFAULT_SCORING_METHODS.get(_clean(source, 20), "计分卡")


def _entry_scoring_method(entry: dict[str, Any]) -> str:
    method = _clean(entry.get("scoring_method"), 10)
    if method in SCORING_METHODS:
        return method
    return DEFAULT_SCORING_METHODS.get(_clean(entry.get("source"), 20), "计分卡")


def _new_entry(
    doc: dict[str, Any],
    *,
    source: str,
    source_id: str,
    source_time: str,
    raw_name: str,
    raw_id: str,
    score: float,
    settled: bool,
    note: str = "",
    weidian: dict[str, Any] | None = None,
    scoring_method: str = "",
    selected_business: str = "",
    selected_business_bonus: str = "",
    status: str = "",
) -> dict[str, Any]:
    entry_id = f"rb-{uuid.uuid4().hex}"
    method = _clean(scoring_method, 10)
    if method not in SCORING_METHODS:
        method = DEFAULT_SCORING_METHODS.get(_clean(source, 20), "计分卡")
    status_key = _clean(status, 20).lower()
    allowed_statuses = ENTRY_STATUS_BY_SOURCE.get(source)
    if allowed_statuses and status_key not in allowed_statuses:
        status_key = allowed_statuses[0]
    entry = {
        "id": entry_id,
        "fan_id": "",
        "fan_name": _clean(raw_name, 120),
        "raw_name": _clean(raw_name, 120),
        "raw_id": _clean(raw_id, 32),
        "score": round(max(0.0, float(score)), 4),
        "source": source,
        "scoring_method": method,
        "source_id": _clean(source_id, 120),
        "source_time": _clean(source_time, 32) or _now(),
        "created_at": _now(),
        "updated_at": _now(),
        "settled": bool(settled),
        "status": status_key,
        "warning": False,
        "warning_reason": "",
        "duplicate": False,
        "duplicate_note": "",
        "business_done": False,
        "business_done_at": "",
        "selected_business": _business_option(selected_business, "card"),
        "selected_business_bonus": _business_option(selected_business_bonus, "bonus"),
        "note": _clean(note),
        "identity_locked": False,
        "ai_suggestion": {},
        "ai_applied_at": "",
        "shipping_error": "",
        "weidian": weidian or {},
    }
    _apply_identity(doc, entry, entry["raw_name"], entry["raw_id"], source=source)
    return entry


def _find_entry(doc: dict[str, Any], source: str, source_id: str) -> dict[str, Any] | None:
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("source") == source and _clean(entry.get("source_id"), 120) == _clean(source_id, 120):
            return entry
    return None


def _upsert_entry(doc: dict[str, Any], candidate: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    existing = _find_entry(doc, candidate["source"], candidate["source_id"])
    if existing is None:
        doc.setdefault("entries", []).append(candidate)
        return candidate, True
    for key in (
        "score",
        "scoring_method",
        "source_time",
        "settled",
        "status",
        "weidian",
        "shipping_error",
    ):
        if key in candidate:
            existing[key] = candidate[key]
    existing["updated_at"] = _now()
    if not existing.get("identity_locked"):
        _apply_identity(
            doc,
            existing,
            candidate.get("raw_name") or existing.get("raw_name"),
            candidate.get("raw_id") or existing.get("raw_id"),
            source=existing.get("source") or candidate.get("source"),
        )
    if not existing.get("note") and candidate.get("note"):
        existing["note"] = candidate["note"]
    return existing, False


def _normalise_entry(entry: dict[str, Any], aliases: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    source = _clean(entry.get("source"), 20)
    scoring_method = _entry_scoring_method(entry)
    status = _entry_status(entry)
    raw_name = _clean(entry.get("raw_name"), 120)
    raw_id = _clean(entry.get("raw_id"), 32)
    fan_id = _clean(entry.get("fan_id"), 32)
    fan_name = _clean(entry.get("fan_name") or raw_name, 120)
    warning = bool(entry.get("warning"))
    warning_reason = _clean(entry.get("warning_reason"))
    if not entry.get("identity_locked"):
        resolved = _resolve_identity(raw_name, fan_id or raw_id, ())
        if resolved["warning"] and aliases:
            resolved = _resolve_identity(raw_name, fan_id or raw_id, aliases)
        if not resolved["warning"]:
            fan_id = resolved["fan_id"] or fan_id
            fan_name = resolved["fan_name"] or fan_name
            warning = False
            warning_reason = ""
    return {
        "id": _clean(entry.get("id"), 80),
        "fan_id": fan_id,
        "fan_name": fan_name,
        "raw_name": raw_name,
        "raw_id": raw_id,
        "score": round(_to_float(entry.get("score"), 0.0), 4),
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "scoring_method": scoring_method,
        "scoring_method_note": _clean(entry.get("scoring_method_note")),
        "scoring_method_overridden_at": _clean(entry.get("scoring_method_overridden_at"), 32),
        "scoring_evidence": [
            _clean(item, 80)
            for item in (entry.get("scoring_evidence") if isinstance(entry.get("scoring_evidence"), list) else [])
            if EVIDENCE_NAME_RE.fullmatch(_clean(item, 80))
        ],
        "source_scoring_label": (
            f"{SCORING_SOURCE_LABELS.get(source, SOURCE_LABELS.get(source, source))}·{scoring_method}"
            if scoring_method
            else SCORING_SOURCE_LABELS.get(source, SOURCE_LABELS.get(source, source))
        ),
        "source_id": _clean(entry.get("source_id"), 120),
        "source_time": _clean(entry.get("source_time"), 32),
        "created_at": _clean(entry.get("created_at"), 32),
        "updated_at": _clean(entry.get("updated_at"), 32),
        "settled": _entry_settled(entry),
        "status": status,
        "status_label": ENTRY_STATUS_LABELS.get(status, status),
        "warning": warning,
        "warning_reason": warning_reason,
        "duplicate": bool(entry.get("duplicate")),
        "duplicate_note": _clean(entry.get("duplicate_note")),
        "is_association": source in ASSOCIATION_SOURCES,
        "proxy_settlement": (
            entry.get("proxy_settlement")
            if isinstance(entry.get("proxy_settlement"), dict)
            else {}
        ),
        "business_done": bool(entry.get("business_done")),
        "business_done_at": _clean(entry.get("business_done_at"), 32),
        "selected_business": _clean(entry.get("selected_business"), 80),
        "selected_business_bonus": _clean(entry.get("selected_business_bonus"), 80),
        "note": _clean(entry.get("note")),
        "identity_locked": bool(entry.get("identity_locked")),
        "ai_suggestion": entry.get("ai_suggestion") if isinstance(entry.get("ai_suggestion"), dict) else {},
        "ai_applied_at": _clean(entry.get("ai_applied_at"), 32),
        "shipping_error": _clean(entry.get("shipping_error")),
        "weidian": entry.get("weidian") if isinstance(entry.get("weidian"), dict) else {},
    }


# ── 筛选与汇总 ──────────────────────────────────────────────────────────


def _format_score(value: float) -> str:
    number = float(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _parse_scores(value: Any) -> set[float]:
    """解析逗号分隔的分数筛选（多选），忽略非法值。"""
    if isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = str(value or "").split(",")
    scores: set[float] = set()
    for part in parts:
        text = part.strip()
        if not text:
            continue
        try:
            number = float(text)
        except ValueError:
            continue
        if number > 0:
            scores.add(round(number, 4))
    return scores


def _filter_entries(
    entries: Iterable[dict[str, Any]],
    *,
    source: str = "all",
    status_filter: str = "all",
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
    include_duplicate: bool = True,
    scores: set[float] | None = None,
    aliases: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    source = _clean(source, 20).lower() or "all"
    status_filter = _clean(status_filter, 20).lower() or "all"
    keyword = _clean(keyword, 120).casefold()
    wanted_scores = {round(value, 4) for value in (scores or set())}
    result: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        item = _normalise_entry(raw, aliases)
        if source != "all" and item["source"] != source:
            continue
        if not include_duplicate and item["duplicate"]:
            continue
        if wanted_scores and round(_to_float(item.get("score"), 0.0), 4) not in wanted_scores:
            continue
        if status_filter == "settled" and not item["settled"]:
            continue
        if status_filter == "pending" and item["settled"]:
            continue
        if status_filter in {"unshipped", "shipped", "paid"} and item["status"] != status_filter:
            continue
        if status_filter == "warning" and not item["warning"]:
            continue
        if status_filter == "duplicate" and not item["duplicate"]:
            continue
        if status_filter == "normal" and (item["warning"] or item["duplicate"]):
            continue
        day = (item["source_time"] or item["created_at"])[:10]
        if date_from and day < date_from:
            continue
        if date_to and day > date_to:
            continue
        if keyword:
            haystack = " ".join(
                [
                    item["fan_name"],
                    item["fan_id"],
                    item["raw_name"],
                    item["raw_id"],
                    item["note"],
                    item["source_id"],
                    item["weidian"].get("buyer_name", ""),
                    item["weidian"].get("buyer_note", ""),
                ]
            ).casefold()
            if keyword not in haystack:
                continue
        result.append(item)
    return result


def _summary(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = [item for item in entries if isinstance(item, dict) and not item.get("duplicate")]
    settled = [item for item in items if item.get("settled")]
    pending = [item for item in items if not item.get("settled")]
    people = {_entry_key(item) for item in items}
    return {
        "entry_count": len(items),
        "people_count": len(people),
        "total_score": round(sum(_to_float(item.get("score"), 0.0) for item in items), 4),
        "settled_score": round(sum(_to_float(item.get("score"), 0.0) for item in settled), 4),
        "pending_score": round(sum(_to_float(item.get("score"), 0.0) for item in pending), 4),
        "warning_count": sum(1 for item in items if item.get("warning")),
        "pending_count": len(pending),
        "duplicate_count": sum(1 for item in entries if isinstance(item, dict) and item.get("duplicate")),
    }


def _daily_record(item: dict[str, Any]) -> dict[str, Any]:
    weidian = item.get("weidian") if isinstance(item.get("weidian"), dict) else {}
    method = _entry_scoring_method(item)
    source = _clean(item.get("source"), 20)
    source_label = _clean(item.get("source_scoring_label"), 40)
    if not source_label:
        source_label = f"{SCORING_SOURCE_LABELS.get(source, SOURCE_LABELS.get(source, source))}·{method}"
    return {
        "time": _entry_time(item)[11:19],
        "fan_name": _clean(item.get("fan_name") or item.get("raw_name") or "未登记", 120),
        "source": source,
        "source_label": source_label,
        "scoring_method": method,
        "score": round(_to_float(item.get("score"), 0.0), 4),
        "note": _clean(item.get("note"), 200),
        "sku_title": _clean(weidian.get("sku_title"), 80),
        "quantity": _to_float(weidian.get("quantity"), 0.0),
        "weidian_score": _to_float(weidian.get("score"), 0.0),
    }


def _daily_scoring(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """全部条目按天汇总 6 类计分来源，从最早记录连续补到今天。"""
    buckets: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}
    records: dict[str, list[dict[str, Any]]] = {}
    for item in entries:
        if not isinstance(item, dict) or item.get("duplicate"):
            continue
        key = f"{item.get('source') or ''}|{_entry_scoring_method(item)}"
        if key not in DAILY_SCORING_KEYS:
            continue
        day = _entry_time(item)[:10]
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            continue
        bucket = buckets.setdefault(day, {})
        bucket[key] = round(bucket.get(key, 0.0) + _to_float(item.get("score"), 0.0), 4)
        counts[day] = counts.get(day, 0) + 1
        records.setdefault(day, []).append(_daily_record(item))
    for day_records in records.values():
        day_records.sort(key=lambda record: record["time"])
    if not buckets:
        return {
            "start": "",
            "end": "",
            "categories": [dict(item) for item in DAILY_SCORING_CATEGORIES],
            "days": [],
            "total_score": 0.0,
            "entry_count": 0,
        }

    start = datetime.strptime(min(buckets), "%Y-%m-%d").date()
    latest = datetime.strptime(max(buckets), "%Y-%m-%d").date()
    today = datetime.now(BJ_TZ).date()
    end = max(latest, today)
    days: list[dict[str, Any]] = []
    total_score = 0.0
    cursor = start
    while cursor <= end:
        day = cursor.isoformat()
        scores = {item["key"]: round(buckets.get(day, {}).get(item["key"], 0.0), 4) for item in DAILY_SCORING_CATEGORIES}
        day_total = round(sum(scores.values()), 4)
        total_score = round(total_score + day_total, 4)
        days.append(
            {
                "date": day,
                "scores": scores,
                "total": day_total,
                "count": counts.get(day, 0),
                "records": records.get(day, []),
            }
        )
        cursor += timedelta(days=1)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "categories": [dict(item) for item in DAILY_SCORING_CATEGORIES],
        "days": days,
        "total_score": total_score,
        "entry_count": sum(counts.values()),
    }


def _fan_summary(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict) or item.get("duplicate"):
            continue
        key = _entry_key(item)
        group = groups.setdefault(
            key,
            {
                "key": key,
                "fan_id": item.get("fan_id") or "",
                "fan_name": item.get("fan_name") or item.get("raw_name") or "未登记",
                "total_score": 0.0,
                "settled_score": 0.0,
                "pending_score": 0.0,
                "entry_count": 0,
                "warning": False,
                "sources": {},
                "scoring": {},
                "score_names": [],
                "score_name": "",
                "reached_at": "",
                "_score_time": "",
            },
        )
        score = _to_float(item.get("score"), 0.0)
        group["total_score"] = round(group["total_score"] + score, 4)
        if item.get("settled"):
            group["settled_score"] = round(group["settled_score"] + score, 4)
        else:
            group["pending_score"] = round(group["pending_score"] + score, 4)
        group["entry_count"] += 1
        group["warning"] = group["warning"] or bool(item.get("warning"))
        source = item.get("source") or ""
        group["sources"][source] = round(group["sources"].get(source, 0.0) + score, 4)
        method = _entry_scoring_method(item)
        group["scoring"][method] = round(group["scoring"].get(method, 0.0) + score, 4)
        raw_name = _clean(item.get("raw_name") or item.get("fan_name"), 120)
        if raw_name and raw_name not in group["score_names"]:
            group["score_names"].append(raw_name)
        item_time = _entry_time(item)
        if item_time >= str(group["reached_at"]):
            group["reached_at"] = item_time
        if raw_name and item_time >= str(group["_score_time"]):
            group["_score_time"] = item_time
            group["score_name"] = raw_name
        if not group["fan_id"] and item.get("fan_id"):
            group["fan_id"] = item["fan_id"]
    for group in groups.values():
        group.pop("_score_time", None)
    return sorted(
        groups.values(),
        key=lambda row: (
            -_to_float(row.get("total_score"), 0.0),
            str(row.get("reached_at") or "9999-12-31 23:59:59"),
            str(row.get("fan_name")),
        ),
    )


def _sort_entries(entries: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    reverse = _clean(sort, 20).lower() == "time_desc"
    return sorted(
        entries,
        key=lambda item: (_entry_time(item), item.get("id") or ""),
        reverse=reverse,
    )


def _load_filtered(
    *,
    source: str,
    status_filter: str,
    keyword: str,
    date_from: str,
    date_to: str,
    sort: str,
    include_duplicate: bool,
    scores: set[float] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        doc = load_document(RESOURCE)
    except SharedStateError as exc:
        logger.warning("redblue ledger load failed: %s", exc)
        raise HTTPException(status_code=503, detail="红蓝台账暂时不可用，请稍后重试") from exc
    filtered = _filter_entries(
        doc.get("entries") or [],
        source=source,
        status_filter=status_filter,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        include_duplicate=include_duplicate,
        scores=scores,
        aliases=doc.get("aliases") or [],
    )
    return doc, _sort_entries(filtered, sort)


# ── Mutators ────────────────────────────────────────────────────────────


def _norm_override_time(value: Any) -> str:
    text = _clean(value, 32).replace("T", " ")
    if len(text) == 16:
        text += ":00"
    return text


def _scoring_override_matches(
    doc: dict[str, Any],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """按昵称/ID + 时间窗 + 礼物名找房间/直播条目，用于鸡腿凭证改判。"""
    name = _clean(payload.get("name"), 120)
    fan_id = _clean(payload.get("fan_id") or payload.get("id"), 32)
    gift_name = _clean(payload.get("gift_name"), 160) or "弦月回响"
    start = _norm_override_time(payload.get("start"))
    end = _norm_override_time(payload.get("end"))
    method = _clean(payload.get("method"), 10)
    if not name and not fan_id:
        raise ValueError("请填写口袋48昵称或 ID")
    if method not in SCORING_METHODS:
        raise ValueError("计分方式无效")
    matches: list[dict[str, Any]] = []
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if _clean(entry.get("source"), 20) not in {"room", "live"}:
            continue
        note = _clean(entry.get("note"))
        if gift_name and gift_name not in note:
            continue
        names = {
            _clean(entry.get("raw_name"), 120),
            _clean(entry.get("fan_name"), 120),
        }
        ids = {
            _clean(entry.get("raw_id"), 32),
            _clean(entry.get("fan_id"), 32),
        }
        if name and name not in names:
            continue
        if fan_id and fan_id not in ids:
            continue
        source_time = _clean(entry.get("source_time"), 32)
        if start and source_time < start:
            continue
        if end and source_time > end:
            continue
        matches.append(entry)
    return matches


def _mutator_override_scoring(doc: dict[str, Any], payload: dict[str, Any]):
    method = _clean(payload.get("method"), 10)
    if method not in SCORING_METHODS:
        raise ValueError("计分方式无效")
    matches = _scoring_override_matches(doc, payload)
    if not matches:
        raise ValueError("没有匹配的条目，请检查昵称/ID、礼物名和时间窗")
    note = _clean(payload.get("note"), 200)
    now = _now()
    for entry in matches:
        entry["scoring_method"] = method
        entry["scoring_method_note"] = note
        entry["scoring_method_overridden_at"] = now
        entry["updated_at"] = now
    return doc, {
        "matched": len(matches),
        "updated": len(matches),
        "method": method,
        "total_score": round(sum(_to_float(entry.get("score"), 0.0) for entry in matches), 4),
        "entry_ids": [_clean(entry.get("id"), 80) for entry in matches],
    }


def _mutator_set_scoring_method(doc: dict[str, Any], payload: dict[str, Any]):
    raw_ids = payload.get("entry_ids")
    if not isinstance(raw_ids, list):
        raise ValueError("请选择要改判的条目")
    entry_ids = {_clean(value, 80) for value in raw_ids if _clean(value, 80)}
    if not entry_ids:
        raise ValueError("请选择要改判的条目")
    method = _clean(payload.get("method"), 10)
    if method not in {"toggle", *SCORING_METHODS}:
        raise ValueError("计分方式无效")
    evidence = [
        _clean(item, 80)
        for item in (payload.get("evidence") if isinstance(payload.get("evidence"), list) else [])
        if EVIDENCE_NAME_RE.fullmatch(_clean(item, 80))
    ]
    note = _clean(payload.get("note"), 200)
    now = _now()
    updated = 0
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict) or _clean(entry.get("id"), 80) not in entry_ids:
            continue
        current = _entry_scoring_method(entry)
        target = ("鸡腿" if current == "计分卡" else "计分卡") if method == "toggle" else method
        entry["scoring_method"] = target
        entry["scoring_method_note"] = note or ("一键切换" if method == "toggle" else "")
        entry["scoring_method_overridden_at"] = now
        existing = entry.get("scoring_evidence") if isinstance(entry.get("scoring_evidence"), list) else []
        merged = [_clean(item, 80) for item in existing if EVIDENCE_NAME_RE.fullmatch(_clean(item, 80))]
        for name in evidence:
            if name not in merged:
                merged.append(name)
        entry["scoring_evidence"] = merged
        entry["updated_at"] = now
        updated += 1
    if not updated:
        raise ValueError("未找到条目")
    return doc, {
        "updated": updated,
        "method": method,
        "evidence": evidence,
    }


def _mutator_add(doc: dict[str, Any], payload: dict[str, Any]):
    raw_name = _clean(payload.get("raw_name"), 120)
    raw_id = _clean(payload.get("raw_id"), 32)
    score = _to_float(payload.get("score"), 0.0)
    if score <= 0:
        raise ValueError("分数必须大于 0")
    if not raw_name and not raw_id:
        raise ValueError("请填写口袋48昵称或 ID")
    source = _clean(payload.get("source"), 20) or "manual"
    if source == "weidian_manual":
        source = "association_manual"
    if source not in {"manual", "association_manual"}:
        raise ValueError("手动条目只能选择暗票或应援会（手动）")
    scoring_method = "鸡腿" if source == "association_manual" else "计分卡"
    source_time = _clean(payload.get("source_time"), 32) or _now()
    weidian = {}
    if source == "association_manual":
        raw_weidian = payload.get("weidian") if isinstance(payload.get("weidian"), dict) else {}
        weidian = {
            "order_id": _clean(payload.get("source_id"), 120) or f"weidian-manual-{uuid.uuid4().hex}",
            "item_id": _clean(raw_weidian.get("item_id"), 40),
            "item_name": _clean(raw_weidian.get("item_name"), 160) or "应援会鸡腿·手动补录",
            "sku_title": _clean(raw_weidian.get("sku_title"), 40) or f"{score:g}分（手动）",
            "status": _clean(raw_weidian.get("status"), 40) or "手动登记",
            "buyer_name": raw_name,
            "quantity": _to_float(raw_weidian.get("quantity"), 1.0) or 1.0,
            "score": score,
            "amount": _to_float(raw_weidian.get("amount"), 0.0),
            "unit_price": _to_float(raw_weidian.get("unit_price"), 0.0),
            "discount": _to_float(raw_weidian.get("discount"), 0.0),
            "manual": True,
            "channel": "manual",
            "shipped": False,
            "shipped_at": "",
        }
    entry = _new_entry(
        doc,
        source=source,
        source_id=_clean(payload.get("source_id"), 120)
        or (weidian.get("order_id") if source == "association_manual" else "")
        or f"{source}-{uuid.uuid4().hex}",
        source_time=source_time,
        raw_name=raw_name,
        raw_id=raw_id,
        score=score,
        settled=False if source in ASSOCIATION_SOURCES else _to_bool(payload.get("settled"), True),
        status=(
            _clean(payload.get("status"), 20) or "paid"
            if source in ASSOCIATION_SOURCES
            else ""
        ),
        note=_clean(payload.get("note")),
        weidian=weidian or None,
        scoring_method=scoring_method,
        selected_business=_clean(payload.get("selected_business"), 80),
        selected_business_bonus=_clean(payload.get("selected_business_bonus"), 80),
    )
    doc.setdefault("entries", []).append(entry)
    return doc, _normalise_entry(entry, doc.get("aliases") or [])


def _mutator_update(doc: dict[str, Any], payload: dict[str, Any]):
    entry_id = _clean(payload.get("id"), 80)
    entry = next((item for item in doc.get("entries") or [] if isinstance(item, dict) and item.get("id") == entry_id), None)
    if entry is None:
        raise ValueError("条目不存在")
    raw_name = _clean(payload.get("raw_name", entry.get("raw_name")), 120)
    raw_id = _clean(payload.get("raw_id", entry.get("raw_id")), 32)
    old_identity = (_clean(entry.get("raw_name"), 120), _clean(entry.get("raw_id"), 32))
    if (raw_name, raw_id) != old_identity:
        entry["identity_locked"] = True
    _apply_identity(doc, entry, raw_name, raw_id, source=entry.get("source") or "manual")
    if payload.get("score") is not None:
        score = _to_float(payload.get("score"), 0.0)
        if score <= 0:
            raise ValueError("分数必须大于 0")
        entry["score"] = round(score, 4)
    if payload.get("note") is not None:
        entry["note"] = _clean(payload.get("note"))
    source = _clean(entry.get("source"), 20)
    if payload.get("status") is not None:
        status = _clean(payload.get("status"), 20).lower()
        allowed_statuses = ENTRY_STATUS_BY_SOURCE.get(source)
        if allowed_statuses:
            if status not in allowed_statuses:
                raise ValueError("状态无效")
            entry["status"] = status
    if payload.get("settled") is not None and source not in ASSOCIATION_SOURCES:
        entry["settled"] = _to_bool(payload.get("settled"), bool(entry.get("settled")))
    if payload.get("duplicate") is not None:
        if source in ASSOCIATION_SOURCES:
            raise ValueError("应援会来源条目不能标记重复")
        if entry.get("proxy_settlement"):
            raise ValueError("已代投的条目不能通过编辑修改重复状态")
        entry["duplicate"] = _to_bool(payload.get("duplicate"), bool(entry.get("duplicate")))
    if payload.get("duplicate_note") is not None:
        entry["duplicate_note"] = _clean(payload.get("duplicate_note"))
    if payload.get("business_done") is not None:
        entry["business_done"] = _to_bool(payload.get("business_done"), bool(entry.get("business_done")))
        entry["business_done_at"] = _now() if entry["business_done"] else ""
    if payload.get("selected_business") is not None:
        entry["selected_business"] = _business_option(payload.get("selected_business"), "card")
    if payload.get("selected_business_bonus") is not None:
        entry["selected_business_bonus"] = _business_option(payload.get("selected_business_bonus"), "bonus")
    entry["updated_at"] = _now()
    return doc, _normalise_entry(entry, doc.get("aliases") or [])


def _mutator_delete(doc: dict[str, Any], payload: dict[str, Any]):
    entry_id = _clean(payload.get("id"), 80)
    before = len(doc.get("entries") or [])
    doc["entries"] = [item for item in doc.get("entries") or [] if not (isinstance(item, dict) and item.get("id") == entry_id)]
    return doc, {"deleted": before - len(doc["entries"])}


def _participant_keys_from_payload(payload: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    rows = payload.get("participants")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _fan_business_key(row.get("fan_id"), row.get("fan_name"))
            if key and key not in keys:
                keys.append(key)
    return keys


def _mutator_upsert_redemption(doc: dict[str, Any], payload: dict[str, Any]):
    redemptions = doc.setdefault("business_redemptions", [])
    if not isinstance(redemptions, list):
        redemptions = []
        doc["business_redemptions"] = redemptions
    redemption_id = _clean(payload.get("id"), 80)
    existing = next(
        (item for item in redemptions if isinstance(item, dict) and _clean(item.get("id"), 80) == redemption_id),
        None,
    )
    if existing is None:
        redemption_id = redemption_id or f"rbr-{uuid.uuid4().hex}"
    source = existing or {}
    entries = [item for item in doc.get("entries") or [] if isinstance(item, dict)]
    entry_map = {_clean(item.get("id"), 80): item for item in entries if _clean(item.get("id"), 80)}
    participant_keys = _participant_keys_from_payload(payload)
    if not participant_keys:
        key = _fan_business_key(
            _clean(payload.get("fan_id") or source.get("fan_id"), 32),
            _clean(payload.get("fan_name") or source.get("fan_name"), 120),
        )
        if key:
            participant_keys = [key]
    participant_entries = [
        item
        for item in entries
        if not item.get("duplicate") and _entry_fan_key(item) in participant_keys
    ]
    scoring_method = _clean(
        payload.get("scoring_method") if "scoring_method" in payload else source.get("scoring_method"),
        10,
    )
    if scoring_method not in SCORING_METHODS:
        existing_allocations = source.get("allocations") if isinstance(source.get("allocations"), list) else []
        methods = {
            _entry_scoring_method(entry_map[_clean(row.get("entry_id"), 80)])
            for row in existing_allocations
            if isinstance(row, dict) and _clean(row.get("entry_id"), 80) in entry_map
        }
        if len(methods) == 1:
            scoring_method = next(iter(methods))
        else:
            fan_methods = {_entry_scoring_method(item) for item in participant_entries}
            scoring_method = next(iter(fan_methods)) if len(fan_methods) == 1 else ""
    if scoring_method not in SCORING_METHODS:
        raise ValueError("请选择计分方式；拼单只能使用同一种计分方式")
    business = _clean(payload.get("business") or source.get("business"), 80)
    option = BUSINESS_OPTION_MAP.get(business)
    if option is None:
        raise ValueError("请选择有效业务")
    cost = round(_to_float(option.get("score"), 0.0), 4)
    if cost <= 0:
        raise ValueError("业务分值无效")
    status = _redemption_status(payload.get("status") if "status" in payload else source.get("status"))
    if "allocations" in payload:
        allocations = _redemption_allocations_from_payload(payload)
    elif existing is not None:
        allocations = _redemption_allocations_from_payload(existing)
    else:
        allocations = []
    used = _entry_used_scores(redemptions, exclude_id=redemption_id)
    if not allocations:
        if not participant_keys:
            raise ValueError("请选择粉丝")
        if not participant_entries:
            raise ValueError("所选粉丝没有可兑换的计分条目")
        allocations = _auto_allocate_redemption(participant_entries, used, cost, scoring_method)
    seen: set[str] = set()
    total = 0.0
    for row in allocations:
        entry_id = row["entry_id"]
        entry = entry_map.get(entry_id)
        if entry is None or entry.get("duplicate"):
            raise ValueError("分摊条目不存在或已被标记重复")
        if _entry_scoring_method(entry) != scoring_method:
            raise ValueError("拼单只能使用同一种计分方式（当前为" + scoring_method + "）")
        if entry_id in seen:
            raise ValueError("同一条目不能重复分摊")
        seen.add(entry_id)
        amount = _to_float(row.get("score"), 0.0)
        available = round(_to_float(entry.get("score"), 0.0) - used.get(entry_id, 0.0), 4)
        if amount <= 0 or amount > available + 0.0001:
            raise ValueError("分摊分数超过条目可用分数")
        total = round(total + amount, 4)
    if abs(total - cost) > 0.0001:
        raise ValueError(f"分摊合计 {total:g} 与业务分值 {cost:g} 不一致")
    bonus_business = _clean(
        payload.get("bonus_business") if "bonus_business" in payload else source.get("bonus_business"),
        80,
    )
    bonus_option = BONUS_OPTION_MAP.get(bonus_business) if bonus_business else None
    if bonus_business and bonus_option is None:
        raise ValueError("加赠业务无效")
    if bonus_option is not None:
        if not any(_entry_scoring_method(entry_map[entry_id]) == "鸡腿" for entry_id in seen):
            raise ValueError("只有鸡腿条目可以叠加加赠业务")
    now = _now()
    completion_entry_id = _completion_entry_id(allocations, entry_map, cost)
    fan_id = _clean(payload.get("fan_id") or source.get("fan_id"), 32)
    fan_name = _clean(payload.get("fan_name") or source.get("fan_name"), 120)
    if not fan_id and not fan_name:
        owner_entry = entry_map.get(completion_entry_id) or {}
        fan_id = _clean(owner_entry.get("fan_id"), 32)
        fan_name = _entry_fan_name(owner_entry)
    if not fan_name and allocations:
        first_entry = entry_map.get(allocations[0]["entry_id"]) or {}
        fan_id = fan_id or _clean(first_entry.get("fan_id"), 32)
        fan_name = _entry_fan_name(first_entry)
    participants: list[dict[str, Any]] = []
    participant_seen: set[str] = set()
    for row in allocations:
        entry = entry_map.get(row["entry_id"]) or {}
        key = _entry_fan_key(entry)
        if not key or key in participant_seen:
            continue
        participant_seen.add(key)
        participants.append({
            "fan_id": _clean(entry.get("fan_id"), 32),
            "fan_name": _entry_fan_name(entry),
        })
    record = {
        "id": redemption_id,
        "fan_id": fan_id,
        "fan_name": fan_name,
        "participants": participants,
        "business": business,
        "bonus_business": bonus_option["value"] if bonus_option else "",
        "bonus_business_name": str(bonus_option["name"]) if bonus_option else "",
        "scoring_method": scoring_method,
        "group": _clean(option.get("group"), 20),
        "cost": cost,
        "status": status,
        "note": _clean(payload.get("note") if "note" in payload else source.get("note")),
        "allocations": allocations,
        "created_at": _clean(source.get("created_at"), 32) or now,
        "updated_at": now,
        "completed_at": (
            _clean(source.get("completed_at"), 32) or now
            if status == "done"
            else ""
        ),
    }
    if existing is not None:
        redemptions[redemptions.index(existing)] = record
    else:
        redemptions.append(record)
    return doc, {"redemption": _normalise_redemption(record, entry_map), "created": existing is None}


def _mutator_delete_redemption(doc: dict[str, Any], payload: dict[str, Any]):
    redemption_id = _clean(payload.get("id"), 80)
    redemptions = doc.get("business_redemptions") if isinstance(doc.get("business_redemptions"), list) else []
    before = len(redemptions)
    doc["business_redemptions"] = [
        item for item in redemptions
        if not (isinstance(item, dict) and _clean(item.get("id"), 80) == redemption_id)
    ]
    return doc, {"deleted": before - len(doc["business_redemptions"])}


def _mutator_migrate_legacy_business(doc: dict[str, Any], payload: dict[str, Any]):
    redemptions = doc.setdefault("business_redemptions", [])
    if not isinstance(redemptions, list):
        redemptions = []
        doc["business_redemptions"] = redemptions
    entries = [item for item in doc.get("entries") or [] if isinstance(item, dict)]
    migrated_entries = {
        _clean(row.get("entry_id"), 80)
        for redemption in redemptions
        if isinstance(redemption, dict)
        for row in (redemption.get("allocations") or [])
        if isinstance(row, dict)
    }
    now = _now()
    created = 0
    skipped = 0
    cleared = 0
    for entry in entries:
        selected = _clean(entry.get("selected_business"), 80)
        selected_bonus = _clean(entry.get("selected_business_bonus"), 80)
        if not selected and not selected_bonus:
            continue
        entry_id = _clean(entry.get("id"), 80)
        fan_id = _clean(entry.get("fan_id"), 32)
        fan_name = _clean(entry.get("fan_name") or entry.get("raw_name"), 120)
        if not entry_id or (not fan_id and not fan_name) or entry_id in migrated_entries:
            skipped += 1
            continue
        option = BUSINESS_OPTION_MAP.get(selected)
        if option is None or option.get("group") != "card":
            skipped += 1
            continue
        cost = round(_to_float(option.get("score"), 0.0), 4)
        if _to_float(entry.get("score"), 0.0) + 0.0001 < cost:
            skipped += 1
            continue
        bonus_option = BONUS_OPTION_MAP.get(selected_bonus) if selected_bonus else None
        if bonus_option is not None and _entry_scoring_method(entry) != "鸡腿":
            bonus_option = None
        status = "done" if entry.get("business_done") else "pending"
        record = {
            "id": f"rbr-legacy-{entry_id}"[:80],
            "fan_id": fan_id,
            "fan_name": fan_name,
            "business": selected,
            "bonus_business": bonus_option["value"] if bonus_option else "",
            "bonus_business_name": str(bonus_option["name"]) if bonus_option else "",
            "scoring_method": _entry_scoring_method(entry),
            "group": "card",
            "cost": cost,
            "status": status,
            "note": "",
            "legacy_entry_id": entry_id,
            "allocations": [{"entry_id": entry_id, "score": cost}],
            "created_at": _entry_time(entry) or now,
            "updated_at": now,
            "completed_at": (
                _clean(entry.get("business_done_at"), 32) or now
                if status == "done"
                else ""
            ),
        }
        redemptions.append(record)
        migrated_entries.add(entry_id)
        entry["selected_business"] = ""
        entry["selected_business_bonus"] = ""
        entry["business_done"] = False
        entry["business_done_at"] = ""
        created += 1
        cleared += 1
    return doc, {"created": created, "skipped": skipped, "cleared": cleared}


def _mutator_duplicate(doc: dict[str, Any], payload: dict[str, Any]):
    entry_id = _clean(payload.get("id"), 80)
    entry = next((item for item in doc.get("entries") or [] if isinstance(item, dict) and item.get("id") == entry_id), None)
    if entry is None:
        raise ValueError("条目不存在")
    if _clean(entry.get("source"), 20) in ASSOCIATION_SOURCES:
        raise ValueError("应援会来源条目不能标记重复")
    target = _to_bool(payload.get("duplicate"), not bool(entry.get("duplicate")))
    if entry.get("proxy_settlement"):
        raise ValueError("已代投的条目不能通过重复按钮修改")
    entry["duplicate"] = target
    if payload.get("duplicate_note") is not None:
        entry["duplicate_note"] = _clean(payload.get("duplicate_note"))
    if payload.get("business_done") is not None:
        entry["business_done"] = _to_bool(payload.get("business_done"), bool(entry.get("business_done")))
        entry["business_done_at"] = _now() if entry["business_done"] else ""
    entry["updated_at"] = _now()
    return doc, _normalise_entry(entry, doc.get("aliases") or [])


def _mutator_apply_ai(doc: dict[str, Any], payload: dict[str, Any]):
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    entries = {str(item.get("id")): item for item in doc.get("entries") or [] if isinstance(item, dict)}
    applied = 0
    skipped = 0
    for suggestion in items:
        if not isinstance(suggestion, dict):
            continue
        entry = entries.get(_clean(suggestion.get("entry_id"), 80))
        if entry is None:
            skipped += 1
            continue
        fan_id = _clean(suggestion.get("fan_id"), 32)
        fan_name = _clean(suggestion.get("fan_name"), 120)
        resolved = _resolve_identity(fan_name, fan_id, doc.get("aliases") or [])
        if resolved["warning"]:
            skipped += 1
            continue
        entry["fan_id"] = resolved["fan_id"]
        entry["fan_name"] = resolved["fan_name"] or fan_name
        entry["warning"] = False
        entry["warning_reason"] = ""
        entry["identity_locked"] = True
        entry["ai_suggestion"] = {
            "fan_id": resolved["fan_id"],
            "fan_name": resolved["fan_name"] or fan_name,
            "confidence": _to_float(suggestion.get("confidence"), 0.0),
            "reason": _clean(suggestion.get("reason")),
            "evidence": _clean(suggestion.get("evidence")),
            "backend": _clean(suggestion.get("backend"), 20),
        }
        entry["ai_applied_at"] = _now()
        entry["updated_at"] = _now()
        _add_alias(doc, entry.get("raw_name") or entry.get("fan_name"), resolved["fan_id"], resolved["fan_name"], entry.get("source") or "manual")
        applied += 1
    return doc, {"applied": applied, "skipped": skipped}


def _mutator_upsert_room_live(doc: dict[str, Any], payload: dict[str, Any]):
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    created = 0
    updated = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        source = _clean(item.get("source"), 20)
        if source not in {"room", "live"}:
            continue
        source_id = _clean(item.get("source_id"), 120)
        if not source_id:
            continue
        scoring_method = _clean(item.get("scoring_method"), 10)
        if scoring_method not in SCORING_METHODS:
            scoring_method = _gift_scoring_method(
                _clean(item.get("gift_name"), 160),
                source,
                _clean(item.get("gift_id"), 40),
            )
        candidate = _new_entry(
            doc,
            source=source,
            source_id=source_id,
            source_time=_clean(item.get("source_time"), 32),
            raw_name=_clean(item.get("raw_name"), 120),
            raw_id=_clean(item.get("raw_id"), 32),
            score=_to_float(item.get("score"), 0.0),
            settled=True,
            note=_clean(item.get("note")),
            scoring_method=scoring_method,
        )
        _, is_new = _upsert_entry(doc, candidate)
        created += int(is_new)
        updated += int(not is_new)
    return doc, {"created": created, "updated": updated}


def _mutator_upsert_weidian(doc: dict[str, Any], payload: dict[str, Any]):
    orders = payload.get("orders") if isinstance(payload.get("orders"), list) else []
    created = 0
    updated = 0
    for order in orders:
        if not isinstance(order, dict):
            continue
        order_id = _clean(order.get("order_id"), 120)
        if not order_id:
            continue
        buyer_name = _clean(order.get("buyer_name"), 120)
        buyer_note = _clean(order.get("buyer_note"))
        seller_note = _clean(order.get("seller_note"))
        note = buyer_note or seller_note
        # Notes may be used only to find an explicit pocket48 ID; they are
        # never used as the entry name (members often put business requests).
        match = POCKET_ID_RE.search(note) or POCKET_ID_RE.search(buyer_name)
        raw_id = match.group(1) if match else ""
        raw_name = buyer_name
        status_desc = _clean(order.get("status"), 40)
        shipped_at = _clean(order.get("shipped_at"), 32)
        shipped = _weidian_order_shipped(order)
        weidian = {
            "order_id": order_id,
            "item_id": _clean(order.get("item_id"), 40),
            "item_name": _clean(order.get("item_name"), 160),
            "sku_title": _clean(order.get("sku_title"), 40),
            "status": status_desc,
            "buyer_name": buyer_name,
            "buyer_note": buyer_note,
            "seller_note": seller_note,
            "quantity": _to_float(order.get("quantity"), 0.0),
            "score": _weidian_order_score(order),
            "amount": _to_float(order.get("amount"), 0.0),
            "shipped": shipped,
            "shipped_at": shipped_at,
        }
        candidate = _new_entry(
            doc,
            source="weidian",
            source_id=order_id,
            source_time=_clean(order.get("add_time"), 32),
            raw_name=raw_name,
            raw_id=raw_id,
            score=_weidian_order_score(order),
            settled=False,
            status="shipped" if shipped else "unshipped",
            note=note,
            weidian=weidian,
        )
        existing = _find_entry(doc, "weidian", order_id)
        if existing is not None and _entry_status(existing) == "settled":
            candidate["status"] = "settled"
        if existing is not None and existing.get("identity_locked"):
            candidate["identity_locked"] = True
            candidate["fan_id"] = existing.get("fan_id") or candidate.get("fan_id")
            candidate["fan_name"] = existing.get("fan_name") or candidate.get("fan_name")
            candidate["warning"] = bool(existing.get("warning"))
            candidate["warning_reason"] = existing.get("warning_reason") or ""
        _, is_new = _upsert_entry(doc, candidate)
        created += int(is_new)
        updated += int(not is_new)
    return doc, {"created": created, "updated": updated}


def _mutator_rename_weidian(doc: dict[str, Any], payload: dict[str, Any]):
    """Update a Weidian entry's static scoring nickname after a page rename."""
    order_id = _clean(payload.get("order_id"), 120)
    name = _clean(payload.get("name"), 120)
    if not order_id or not name:
        raise ValueError("订单号和播报名不能为空")
    entry = _find_entry(doc, "weidian", order_id)
    if entry is None:
        return doc, {"updated": 0, "reason": "not_found", "order_id": order_id}
    entry["raw_name"] = name
    weidian = entry.get("weidian") if isinstance(entry.get("weidian"), dict) else {}
    weidian["buyer_name"] = name
    entry["weidian"] = weidian
    if not entry.get("identity_locked"):
        _apply_identity(doc, entry, name, _clean(entry.get("raw_id"), 32), source="weidian")
    entry["updated_at"] = _now()
    return doc, {
        "updated": 1,
        "order_id": order_id,
        "scoring_name": name,
        "fan_id": entry.get("fan_id"),
        "fan_name": entry.get("fan_name"),
    }


def _mutator_mark_shipped(doc: dict[str, Any], payload: dict[str, Any]):
    order_ids = {_clean(value, 120) for value in (payload.get("order_ids") or []) if _clean(value, 120)}
    shipped_at = _clean(payload.get("shipped_at"), 32) or _now()
    updated = 0
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("source") != "weidian":
            continue
        if _clean(entry.get("source_id"), 120) not in order_ids:
            continue
        if _entry_status(entry) != "settled":
            entry["status"] = "shipped"
            entry["settled"] = False
        entry["shipping_error"] = ""
        entry["updated_at"] = _now()
        weidian = entry.setdefault("weidian", {})
        if isinstance(weidian, dict):
            weidian["shipped"] = True
            weidian["shipped_at"] = shipped_at
        updated += 1
    return doc, {"updated": updated}


def _mutator_migrate_manual_source(doc: dict[str, Any], payload: dict[str, Any]):
    old_source = _clean(payload.get("old_source"), 20) or "weidian_manual"
    new_source = _clean(payload.get("new_source"), 20) or "association_manual"
    if old_source not in {"weidian_manual", "association_manual"} or new_source != "association_manual":
        raise ValueError("手动来源迁移参数无效")
    now = _now()
    updated = 0
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict) or _clean(entry.get("source"), 20) != old_source:
            continue
        entry["source"] = new_source
        entry["scoring_method"] = "鸡腿"
        entry["updated_at"] = now
        updated += 1
    return doc, {"updated": updated, "old_source": old_source, "new_source": new_source}


register_mutator(RESOURCE, "migrate_manual_source", _mutator_migrate_manual_source)
register_mutator(RESOURCE, "add", _mutator_add)
register_mutator(RESOURCE, "update", _mutator_update)
register_mutator(RESOURCE, "delete", _mutator_delete)
register_mutator(RESOURCE, "duplicate", _mutator_duplicate)
register_mutator(RESOURCE, "settle_association", _mutator_settle_association)
register_mutator(RESOURCE, "apply_ai", _mutator_apply_ai)
register_mutator(RESOURCE, "upsert_room_live", _mutator_upsert_room_live)
register_mutator(RESOURCE, "upsert_weidian", _mutator_upsert_weidian)
register_mutator(RESOURCE, "rename_weidian", _mutator_rename_weidian)
register_mutator(RESOURCE, "mark_shipped", _mutator_mark_shipped)
register_mutator(RESOURCE, "upsert_redemption", _mutator_upsert_redemption)
register_mutator(RESOURCE, "delete_redemption", _mutator_delete_redemption)
register_mutator(RESOURCE, "migrate_legacy_business", _mutator_migrate_legacy_business)
register_mutator(RESOURCE, "override_scoring", _mutator_override_scoring)
register_mutator(RESOURCE, "set_scoring_method", _mutator_set_scoring_method)


def _build_room_live_items() -> list[dict[str, Any]]:
    path = Path(cfg.REDBLUE_SCORE_DATA_PATH)
    if not path.exists():
        return []
    data = _load_json(path)
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        return []
    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        source = _clean(item.get("source"), 20)
        if source not in {"room", "live"}:
            continue
        source_id = _clean(item.get("id"), 120)
        if not source_id:
            continue
        score = _to_float(item.get("total_score"), 0.0)
        if score <= 0:
            continue
        note = _clean(item.get("gift_name"), 160)
        if item.get("gift_count"):
            note = f"{note} × {int(_to_float(item.get('gift_count'), 1))}"
        gift_name = _clean(item.get("gift_name"), 160)
        gift_id = _clean(item.get("gift_id"), 40)
        items.append(
            {
                "source": source,
                "source_id": source_id,
                "source_time": _clean(item.get("event_time"), 32),
                "raw_name": _clean(item.get("sender_name"), 120),
                "raw_id": _clean(item.get("sender_id"), 32),
                "score": score,
                "note": note,
                "gift_name": gift_name,
                "gift_id": gift_id,
                "scoring_method": _gift_scoring_method(gift_name, source, gift_id),
            }
        )
    return items


def _room_live_changed(doc: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    existing = {
        (_clean(entry.get("source"), 20), _clean(entry.get("source_id"), 120)): entry
        for entry in doc.get("entries") or []
        if isinstance(entry, dict)
    }
    for item in items:
        entry = existing.get((item["source"], item["source_id"]))
        if entry is None:
            return True
        if abs(_to_float(entry.get("score"), 0.0) - item["score"]) > 1e-9:
            return True
        if _entry_scoring_method(entry) != item.get("scoring_method"):
            return True
        if _clean(entry.get("source_time"), 32) != item["source_time"]:
            return True
        if _clean(entry.get("raw_name"), 120) != item["raw_name"]:
            return True
        if _clean(entry.get("raw_id"), 32) != item["raw_id"]:
            return True
    return False


def _sync_room_live_now(request: Request | None = None) -> dict[str, Any]:
    with _ROOM_LIVE_SYNC_LOCK:
        items = _build_room_live_items()
        try:
            doc = load_document(RESOURCE)
        except SharedStateError:
            doc = {}
        if not _room_live_changed(doc, items):
            return {"created": 0, "updated": 0, "skipped": True}
        if request is not None:
            return _mutate("upsert_room_live", {"items": items}, request).get("result") or {}
        result = execute_mutation(
            RESOURCE,
            "upsert_room_live",
            {"items": items},
            operation_id=uuid.uuid4().hex,
        )
        return result.get("result") or {}


def _weidian_changed(doc: dict[str, Any], orders: list[dict[str, Any]]) -> bool:
    existing = {
        _clean(entry.get("source_id"), 120): entry
        for entry in doc.get("entries") or []
        if isinstance(entry, dict) and entry.get("source") == "weidian"
    }
    for order in orders:
        if not isinstance(order, dict):
            continue
        order_id = _clean(order.get("order_id"), 120)
        if not order_id:
            continue
        entry = existing.get(order_id)
        if entry is None:
            return True
        if abs(_to_float(entry.get("score"), 0.0) - _weidian_order_score(order)) > 1e-9:
            return True
        weidian = entry.get("weidian") if isinstance(entry.get("weidian"), dict) else {}
        if _clean(weidian.get("status"), 40) != _clean(order.get("status"), 40):
            return True
        expected_status = "shipped" if _weidian_order_shipped(order) else "unshipped"
        current_status = _entry_status(entry)
        if current_status != "settled" and current_status != expected_status:
            return True
        if _clean(weidian.get("item_name"), 160) != _clean(order.get("item_name"), 160):
            return True
        if _clean(weidian.get("sku_title"), 40) != _clean(order.get("sku_title"), 40):
            return True
        if abs(_to_float(weidian.get("quantity"), 0.0) - _to_float(order.get("quantity"), 0.0)) > 1e-9:
            return True
        if _clean(weidian.get("buyer_name"), 120) != _clean(order.get("buyer_name"), 120):
            return True
        if _clean(weidian.get("buyer_note"), 500) != _clean(order.get("buyer_note"), 500):
            return True
        if _clean(weidian.get("seller_note"), 500) != _clean(order.get("seller_note"), 500):
            return True
    return False


# ── 数据接口 ────────────────────────────────────────────────────────────


@router.get("/data")
def get_redblue_data(
    response: Response,
    source: str = Query("all"),
    status_filter: str = Query("all", alias="status"),
    keyword: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sort: str = Query("time_asc"),
    include_duplicate: bool = Query(True),
    scores: str = Query(""),
    _=Depends(verify_redblue_password),
):
    response.headers["Cache-Control"] = "no-store"
    date_from = _norm_date(date_from)
    date_to = _norm_date(date_to)
    parsed_scores = _parse_scores(scores)
    doc, entries = _load_filtered(
        source=source,
        status_filter=status_filter,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        include_duplicate=include_duplicate,
        scores=parsed_scores,
    )
    raw_entries = doc.get("entries") or []
    all_entries = [_normalise_entry(item, doc.get("aliases") or []) for item in raw_entries if isinstance(item, dict)]
    redemptions = _normalise_redemptions(doc.get("business_redemptions") or [], raw_entries)
    _attach_business_allocations(all_entries, redemptions)
    _attach_business_allocations(entries, redemptions)
    fan_summary = _fan_summary(entries)
    _attach_fan_business(fan_summary, redemptions)
    score_options = sorted(
        {
            round(_to_float(item.get("score"), 0.0), 4)
            for item in all_entries
            if _to_float(item.get("score"), 0.0) > 0
        }
    )
    return {
        "generated_at": _clean(doc.get("updated_at"), 32),
        "summary": _summary(entries),
        "overall": _summary(all_entries),
        "daily_scoring": _daily_scoring(all_entries),
        "fan_summary": fan_summary,
        "entries": entries,
        "score_options": score_options,
        "business_options": BUSINESS_OPTIONS,
        "business_redemptions": redemptions,
        "weidian_sync": _weidian_sync_status(),
        "total": len(entries),
        "filters": {
            "source": _clean(source, 20),
            "status": _clean(status_filter, 20),
            "keyword": _clean(keyword, 120),
            "date_from": date_from,
            "date_to": date_to,
            "sort": _clean(sort, 20),
            "include_duplicate": include_duplicate,
            "scores": sorted(parsed_scores),
        },
    }


def _export_context(
    *,
    source: str,
    status_filter: str,
    keyword: str,
    date_from: str,
    date_to: str,
    sort: str,
    include_duplicate: bool,
    scores: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any], str, str, str]:
    date_from = _norm_date(date_from)
    date_to = _norm_date(date_to)
    parsed_scores = _parse_scores(scores)
    doc, entries = _load_filtered(
        source=source,
        status_filter=status_filter,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        include_duplicate=include_duplicate,
        scores=parsed_scores,
    )
    redemptions = _normalise_redemptions(doc.get("business_redemptions") or [], doc.get("entries") or [])
    _attach_business_allocations(entries, redemptions)
    if not entries:
        raise HTTPException(status_code=404, detail="当前筛选条件下没有条目")
    if len(entries) > cfg.REDBLUE_IMAGE_EXPORT_MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"筛选结果 {len(entries)} 条，单张图最多 {cfg.REDBLUE_IMAGE_EXPORT_MAX_ROWS} 条，请缩小范围",
        )
    period = (
        f"{date_from} 至 {date_to}"
        if date_from and date_to
        else (f"{date_from} 起" if date_from else (f"截至 {date_to}" if date_to else "全部时间"))
    )
    filters = []
    if source != "all":
        filters.append("来源：" + SCORING_SOURCE_LABELS.get(source, SOURCE_LABELS.get(source, source)))
    if status_filter != "all":
        filters.append("状态：" + ENTRY_STATUS_LABELS.get(status_filter, status_filter))
    if keyword:
        filters.append("关键词：" + keyword)
    if parsed_scores:
        filters.append("分数：" + "、".join(_format_score(value) for value in sorted(parsed_scores)))
    if not include_duplicate:
        filters.append("不含重复")
    updated = max((item.get("source_time") or item.get("created_at") or "" for item in entries), default="")[:16]
    return entries, _summary(entries), period, " · ".join(filters), updated


def _export_response(png: bytes, filename: str) -> Response:
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/export/summary.png")
def export_redblue_summary(
    source: str = Query("all"),
    status_filter: str = Query("all", alias="status"),
    keyword: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sort: str = Query("time_asc"),
    include_duplicate: bool = Query(True),
    scores: str = Query(""),
    _=Depends(verify_redblue_password),
):
    entries, summary, period, filter_text, updated = _export_context(
        source=source,
        status_filter=status_filter,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        include_duplicate=include_duplicate,
        scores=scores,
    )
    from website.redblue_export import render_summary_png

    png = render_summary_png(
        entries,
        summary=summary,
        fan_summary=_fan_summary(entries),
        period=period,
        filter_text=filter_text,
        updated=updated,
    )
    stamp = datetime.now(BJ_TZ).strftime("%Y%m%d_%H%M")
    return _export_response(png, f"redblue_summary_{stamp}.png")


@router.get("/export/entries.png")
def export_redblue_entries(
    source: str = Query("all"),
    status_filter: str = Query("all", alias="status"),
    keyword: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sort: str = Query("time_asc"),
    include_duplicate: bool = Query(True),
    scores: str = Query(""),
    _=Depends(verify_redblue_password),
):
    entries, summary, period, filter_text, updated = _export_context(
        source=source,
        status_filter=status_filter,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        include_duplicate=include_duplicate,
        scores=scores,
    )
    from website.redblue_export import render_entries_png

    png = render_entries_png(
        entries,
        summary=summary,
        period=period,
        filter_text=filter_text,
        updated=updated,
    )
    stamp = datetime.now(BJ_TZ).strftime("%Y%m%d_%H%M")
    return _export_response(png, f"redblue_entries_{stamp}.png")


# ── 写操作 ──────────────────────────────────────────────────────────────


def _mutate(operation: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    operation_id = _clean(request.headers.get(MUTATION_HEADER), 80) or uuid.uuid4().hex
    try:
        result = execute_mutation(RESOURCE, operation, payload, operation_id=operation_id)
    except SharedStatePeerError as exc:
        logger.warning("redblue mutation peer failed: %s", exc)
        raise HTTPException(status_code=503, detail="主节点暂时不可用，请稍后重试") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_public_detail(exc, "操作失败，请检查输入")) from exc
    except SharedStateError as exc:
        logger.warning("redblue mutation failed: %s", exc)
        raise HTTPException(status_code=503, detail="红蓝台账暂时不可用，请稍后重试") from exc
    return {"result": result.get("result"), "replicated": result.get("replicated", True)}


@router.post("/entries")
def add_entry(request: Request, payload: dict[str, Any] = Body(...), _=Depends(verify_redblue_password)):
    return _mutate("add", payload, request)


@router.patch("/entries/{entry_id}")
def update_entry(entry_id: str, request: Request, payload: dict[str, Any] = Body(...), _=Depends(verify_redblue_password)):
    payload = dict(payload)
    payload["id"] = entry_id
    return _mutate("update", payload, request)


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: str, request: Request, _=Depends(verify_redblue_password)):
    return _mutate("delete", {"id": entry_id}, request)


@router.post("/entries/{entry_id}/duplicate")
def mark_duplicate(entry_id: str, request: Request, payload: dict[str, Any] = Body(default={}), _=Depends(verify_redblue_password)):
    data = dict(payload or {})
    data["id"] = entry_id
    return _mutate("duplicate", data, request)


@router.get("/settlement/preview")
def preview_association_settlement(entry_id: str = Query(""), _=Depends(verify_redblue_password)):
    entry_id = _clean(entry_id, 80)
    if not entry_id:
        raise HTTPException(status_code=422, detail="缺少条目 ID")
    try:
        doc = load_document(RESOURCE)
    except SharedStateError as exc:
        logger.warning("redblue settlement preview load failed: %s", exc)
        raise HTTPException(status_code=503, detail="红蓝台账暂时不可用，请稍后重试") from exc
    try:
        return _settlement_plan(doc, entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/settlement/apply")
def apply_association_settlement(request: Request, payload: dict[str, Any] = Body(default={}), _=Depends(verify_redblue_password)):
    entry_id = _clean(payload.get("entry_id") or payload.get("id"), 80)
    if not entry_id:
        raise HTTPException(status_code=422, detail="缺少条目 ID")
    return _mutate("settle_association", {"entry_id": entry_id}, request)


@router.post("/scoring-overrides/preview")
def preview_scoring_override(payload: dict[str, Any] = Body(...), _=Depends(verify_redblue_password)):
    doc = load_document(RESOURCE)
    matches = _scoring_override_matches(doc, payload)
    method = _clean(payload.get("method"), 10)
    return {
        "matched": len(matches),
        "total_score": round(sum(_to_float(entry.get("score"), 0.0) for entry in matches), 4),
        "method": method if method in SCORING_METHODS else "",
        "entries": [
            {
                "id": _clean(entry.get("id"), 80),
                "source": _clean(entry.get("source"), 20),
                "source_label": SOURCE_LABELS.get(_clean(entry.get("source"), 20), ""),
                "source_time": _clean(entry.get("source_time"), 32),
                "fan_name": _clean(entry.get("raw_name")) or _clean(entry.get("fan_name")),
                "fan_id": _clean(entry.get("raw_id")) or _clean(entry.get("fan_id")),
                "score": round(_to_float(entry.get("score"), 0.0), 4),
                "scoring_method": _entry_scoring_method(entry),
                "note": _clean(entry.get("note")),
            }
            for entry in matches
        ],
    }


@router.post("/scoring-overrides")
def apply_scoring_override(request: Request, payload: dict[str, Any] = Body(...), _=Depends(verify_redblue_password)):
    return _mutate("override_scoring", payload, request)


@router.post("/entries/scoring-method")
def set_entry_scoring_method(request: Request, payload: dict[str, Any] = Body(...), _=Depends(verify_redblue_password)):
    return _mutate("set_scoring_method", payload, request)


@router.post("/scoring-evidence/upload")
async def upload_scoring_evidence(
    file: UploadFile = File(...),
    _=Depends(verify_redblue_password),
):
    if getattr(cfg, "SHARED_STATE_SYNC_ENABLED", False) and not getattr(cfg, "SHARED_STATE_IS_PRIMARY", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="凭证请在腾讯云主节点红蓝台账上传；阿里云为只读副本",
        )
    ext = EVIDENCE_MIME_EXT.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅支持 JPG/PNG/GIF/WebP 图片")
    content = await file.read(EVIDENCE_MAX_BYTES + 1)
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="空文件")
    if len(content) > EVIDENCE_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="图片不能超过 8MB")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (EVIDENCE_DIR / name).write_bytes(content)
    return {"ok": True, "name": name}


@router.get("/scoring-evidence/{filename}")
def get_scoring_evidence(filename: str, _=Depends(verify_redblue_password)):
    if not EVIDENCE_NAME_RE.fullmatch(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="凭证不存在")
    path = EVIDENCE_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="凭证不存在")
    media_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.post("/redemptions")
def add_redemption(request: Request, payload: dict[str, Any] = Body(...), _=Depends(verify_redblue_password)):
    return _mutate("upsert_redemption", payload, request)


@router.patch("/redemptions/{redemption_id}")
def update_redemption(redemption_id: str, request: Request, payload: dict[str, Any] = Body(...), _=Depends(verify_redblue_password)):
    data = dict(payload)
    data["id"] = redemption_id
    return _mutate("upsert_redemption", data, request)


@router.delete("/redemptions/{redemption_id}")
def delete_redemption(redemption_id: str, request: Request, _=Depends(verify_redblue_password)):
    return _mutate("delete_redemption", {"id": redemption_id}, request)


@router.post("/migrate-legacy-business")
def migrate_legacy_business(request: Request, _=Depends(verify_redblue_password)):
    return _mutate("migrate_legacy_business", {}, request)


@router.post("/sync/room-live")
def sync_room_live(request: Request, _=Depends(verify_redblue_password)):
    try:
        return {"result": _sync_room_live_now(request), "replicated": True}
    except SharedStatePeerError as exc:
        logger.warning("redblue room/live peer failed: %s", exc)
        raise HTTPException(status_code=503, detail="主节点暂时不可用，请稍后重试") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_public_detail(exc, "同步失败，请稍后重试")) from exc
    except SharedStateError as exc:
        logger.warning("redblue room/live sync failed: %s", exc)
        raise HTTPException(status_code=503, detail="红蓝台账暂时不可用，请稍后重试") from exc


# ── 队列 ────────────────────────────────────────────────────────────────


def _queue_root(kind: str) -> Path:
    base = cfg.REDBLUE_AI_QUEUE_DIR if kind == "ai" else cfg.REDBLUE_WEIDIAN_QUEUE_DIR
    return Path(base)


def _queue_dirs(kind: str) -> tuple[Path, Path, Path, Path]:
    root = _queue_root(kind)
    pending = root / "pending"
    results = root / "results"
    done = root / "done"
    for path in (pending, results, done):
        path.mkdir(parents=True, exist_ok=True)
    return root, pending, results, done


def _write_job(kind: str, payload: dict[str, Any]) -> str:
    _, pending, _, _ = _queue_dirs(kind)
    job_id = uuid.uuid4().hex
    payload = dict(payload)
    payload["job_id"] = job_id
    payload["created_at"] = _now()
    payload["origin_node"] = cfg.SHARED_STATE_NODE_ID
    path = pending / f"{job_id}.json"
    tmp = pending / f".{job_id}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return job_id


def _read_job_result(kind: str, job_id: str) -> dict[str, Any]:
    _, pending, results, _ = _queue_dirs(kind)
    result_path = results / f"{job_id}.json"
    if result_path.exists():
        data = _load_json(result_path)
        if isinstance(data, dict):
            return data
        return {"status": "error", "error": "结果文件格式无效"}
    if (pending / f"{job_id}.json").exists():
        return {"status": "pending"}
    return {"status": "missing"}


def _worker_health(kind: str) -> dict[str, Any]:
    root = _queue_root(kind)
    status_path = root / "worker_status.json"
    data = _load_json(status_path)
    return {
        "queue_dir": str(root),
        "worker_status": data if isinstance(data, dict) else {},
        "available": bool(isinstance(data, dict) and data.get("updated_at")),
    }


# ── AI 昵称分析 ─────────────────────────────────────────────────────────


@router.post("/ai/jobs")
def create_ai_job(payload: dict[str, Any] = Body(default={}), _=Depends(verify_redblue_password)):
    entry_ids = {_clean(value, 80) for value in (payload.get("entry_ids") or []) if _clean(value, 80)}
    doc = load_document(RESOURCE)
    selected = []
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry_ids and entry.get("id") not in entry_ids:
            continue
        if not entry_ids and not entry.get("warning"):
            continue
        if not entry.get("warning") and not payload.get("force"):
            continue
        selected.append(_normalise_entry(entry, doc.get("aliases") or []))
    if not selected:
        raise HTTPException(status_code=422, detail="没有需要分析的未登记条目")
    selected = selected[: max(1, int(cfg.REDBLUE_AI_MAX_ENTRIES))]
    job_id = _write_job(
        "ai",
        {
            "type": "identity_resolve",
            "identity_index_path": str(cfg.REDBLUE_IDENTITY_INDEX_PATH),
            "identity_fallback_paths": dict(cfg.REDBLUE_IDENTITY_FALLBACK_PATHS or {}),
            "entries": [
                {
                    "entry_id": item["id"],
                    "raw_name": item["raw_name"] or item["fan_name"],
                    "raw_id": item["raw_id"],
                    "note": item["note"],
                    "source": item["source"],
                    "source_time": item["source_time"],
                    "weidian": item.get("weidian") or {},
                }
                for item in selected
            ],
        },
    )
    return {"job_id": job_id, "count": len(selected)}


@router.get("/ai/jobs/{job_id}")
def get_ai_job(job_id: str, _=Depends(verify_redblue_password)):
    job_id = _valid_job_id(job_id)
    return _read_job_result("ai", job_id)


@router.post("/ai/jobs/{job_id}/apply")
def apply_ai_job(job_id: str, request: Request, _=Depends(verify_redblue_password)):
    job_id = _valid_job_id(job_id)
    result = _read_job_result("ai", job_id)
    if result.get("status") != "done":
        raise HTTPException(status_code=409, detail="AI 任务尚未完成")
    suggestions = result.get("suggestions") if isinstance(result.get("suggestions"), list) else []
    items = []
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        items.append(
            {
                "entry_id": _clean(suggestion.get("entry_id"), 80),
                "fan_id": _clean(suggestion.get("fan_id"), 32),
                "fan_name": _clean(suggestion.get("fan_name"), 120),
                "confidence": _to_float(suggestion.get("confidence"), 0.0),
                "reason": _clean(suggestion.get("reason")),
                "evidence": _clean(suggestion.get("evidence")),
                "backend": _clean(result.get("backend"), 20),
            }
        )
    if not items:
        raise HTTPException(status_code=422, detail="没有可应用的 AI 建议")
    return _mutate("apply_ai", {"items": items}, request)


@router.post("/ai/apply")
def apply_ai_suggestions(request: Request, payload: dict[str, Any] = Body(default={}), _=Depends(verify_redblue_password)):
    entry_ids = {_clean(value, 80) for value in (payload.get("entry_ids") or []) if _clean(value, 80)}
    job_id = _clean(payload.get("job_id"), 64)
    suggestions: list[dict[str, Any]] = []
    backend = ""
    if job_id:
        job_id = _valid_job_id(job_id)
        result = _read_job_result("ai", job_id)
        if result.get("status") != "done":
            raise HTTPException(status_code=409, detail="AI 任务尚未完成")
        backend = _clean(result.get("backend"), 20)
        for suggestion in result.get("suggestions") or []:
            if not isinstance(suggestion, dict):
                continue
            entry_id = _clean(suggestion.get("entry_id"), 80)
            if entry_ids and entry_id not in entry_ids:
                continue
            suggestions.append(
                {
                    "entry_id": entry_id,
                    "fan_id": _clean(suggestion.get("fan_id"), 32),
                    "fan_name": _clean(suggestion.get("fan_name"), 120),
                    "confidence": _to_float(suggestion.get("confidence"), 0.0),
                    "reason": _clean(suggestion.get("reason")),
                    "evidence": _clean(suggestion.get("evidence")),
                    "backend": backend,
                }
            )
    else:
        raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            entry_id = _clean(item.get("entry_id"), 80)
            if entry_ids and entry_id not in entry_ids:
                continue
            suggestions.append(
                {
                    "entry_id": entry_id,
                    "fan_id": _clean(item.get("fan_id"), 32),
                    "fan_name": _clean(item.get("fan_name"), 120),
                    "confidence": _to_float(item.get("confidence"), 0.0),
                    "reason": _clean(item.get("reason")),
                    "evidence": _clean(item.get("evidence")),
                    "backend": _clean(item.get("backend"), 20) or backend,
                }
            )
    if not suggestions:
        raise HTTPException(status_code=422, detail="没有可应用的 AI 建议")
    return _mutate("apply_ai", {"items": suggestions}, request)


@router.get("/ai/prompt")
def ai_prompt(_=Depends(verify_redblue_password)):
    path = Path(cfg.REDBLUE_AI_PROMPT_PATH)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("redblue AI prompt read failed: %s", exc)
        raise HTTPException(status_code=503, detail="AI Prompt 文档暂时不可用") from exc
    return {"path": str(path), "text": text}


@router.get("/ai/health")
def ai_health(_=Depends(verify_redblue_password)):
    return _worker_health("ai")


# ── 微店同步与发货 ──────────────────────────────────────────────────────


@router.post("/weidian/sync")
def create_weidian_sync_job(_=Depends(verify_redblue_password)):
    payload = {
        "type": "sync",
        "item_id": cfg.REDBLUE_WEIDIAN_ITEM_ID,
        "item_ids": list(cfg.REDBLUE_WEIDIAN_ITEM_IDS),
        "output_path": cfg.REDBLUE_WEIDIAN_ORDERS_PATH,
    }
    if _primary():
        job_id = _write_job("weidian", payload)
    else:
        job_id = _clean(_peer_weidian("job-submit", payload).get("job_id"), 64)
    return {"job_id": job_id}


@router.get("/weidian/jobs/{job_id}")
def get_weidian_job(job_id: str, _=Depends(verify_redblue_password)):
    job_id = _valid_job_id(job_id)
    if _primary():
        result = _read_job_result("weidian", job_id)
        _record_weidian_job_result(result, job_id)
        return result
    return _peer_weidian("job-result", {"job_id": job_id})


@router.post("/weidian/sync/apply")
def apply_weidian_sync(request: Request, payload: dict[str, Any] = Body(default={}), _=Depends(verify_redblue_password)):
    job_id = _valid_job_id(_clean(payload.get("job_id"), 64))
    if _primary():
        result = _read_job_result("weidian", job_id)
    else:
        result = _peer_weidian("job-result", {"job_id": job_id})
    if result.get("status") != "done":
        raise HTTPException(status_code=409, detail="微店同步任务尚未完成")
    if _primary():
        path = Path(cfg.REDBLUE_WEIDIAN_ORDERS_PATH)
        data = _load_json(path) if path.exists() else {}
    else:
        data = _peer_weidian("redblue-cache", {"path": cfg.REDBLUE_WEIDIAN_ORDERS_PATH})
    orders = data.get("orders") if isinstance(data, dict) else None
    if not isinstance(orders, list):
        raise HTTPException(status_code=503, detail="微店订单文件格式无效")
    try:
        doc = load_document(RESOURCE)
    except SharedStateError:
        doc = {}
    if not _weidian_changed(doc, orders):
        applied = {"created": 0, "updated": 0, "skipped": True}
        _mark_weidian_sync_applied(data if isinstance(data, dict) else {}, applied)
        return {"result": applied, "replicated": True}
    mutation = _mutate("upsert_weidian", {"orders": orders}, request)
    _mark_weidian_sync_applied(
        data if isinstance(data, dict) else {},
        mutation.get("result") if isinstance(mutation.get("result"), dict) else {},
    )
    return mutation


@router.post("/weidian/ship")
def create_weidian_ship_job(payload: dict[str, Any] = Body(default={}), _=Depends(verify_redblue_password)):
    entry_ids = {_clean(value, 80) for value in (payload.get("entry_ids") or []) if _clean(value, 80)}
    if not entry_ids:
        raise HTTPException(status_code=422, detail="请选择要发货的微店条目")
    try:
        doc = load_document(RESOURCE)
    except SharedStateError as exc:
        logger.warning("redblue ship load failed: %s", exc)
        raise HTTPException(status_code=503, detail="红蓝台账暂时不可用，请稍后重试") from exc
    orders = []
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("id") not in entry_ids:
            continue
        if entry.get("source") != "weidian":
            continue
        if _entry_status(entry) in {"shipped", "settled"}:
            continue
        weidian = entry.get("weidian") or {}
        order_id = _clean(weidian.get("order_id") or entry.get("source_id"), 120)
        item_id = _clean(weidian.get("item_id"), 40) or cfg.REDBLUE_WEIDIAN_ITEM_ID
        if order_id:
            orders.append({"order_id": order_id, "item_id": item_id})
    orders = sorted({(item["order_id"], item["item_id"]) for item in orders})[:200]
    if not orders:
        raise HTTPException(status_code=422, detail="所选条目没有待发货的微店订单")
    payload = {
        "type": "ship",
        "item_id": cfg.REDBLUE_WEIDIAN_ITEM_ID,
        "orders": [{"order_id": order_id, "item_id": item_id} for order_id, item_id in orders],
    }
    if _primary():
        job_id = _write_job("weidian", payload)
    else:
        job_id = _clean(_peer_weidian("job-submit", payload).get("job_id"), 64)
    return {"job_id": job_id, "count": len(orders)}


@router.post("/weidian/ship/apply")
def apply_weidian_ship(request: Request, payload: dict[str, Any] = Body(default={}), _=Depends(verify_redblue_password)):
    job_id = _valid_job_id(_clean(payload.get("job_id"), 64))
    if _primary():
        result = _read_job_result("weidian", job_id)
    else:
        result = _peer_weidian("job-result", {"job_id": job_id})
    if result.get("status") != "done":
        raise HTTPException(status_code=409, detail="微店发货任务尚未完成")
    shipped = result.get("shipped") if isinstance(result.get("shipped"), list) else []
    order_ids = sorted({_clean(item.get("order_id"), 120) for item in shipped if isinstance(item, dict) and item.get("order_id")})
    if not order_ids:
        return {"updated": 0, "errors": result.get("errors") or []}
    mutation = _mutate("mark_shipped", {"order_ids": order_ids, "shipped_at": _now()}, request)
    return {"updated": mutation.get("result", {}).get("updated", 0), "errors": result.get("errors") or []}


@router.get("/weidian/health")
def weidian_health(_=Depends(verify_redblue_password)):
    return _worker_health("weidian")

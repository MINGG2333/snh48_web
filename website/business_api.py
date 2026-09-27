"""应援会业务管理页 API。

数据含暗账粉丝名单，只保存在腾讯云本地非 Git 目录（BUSINESS_DATA_PATH），
通过 shared_runtime_state 写回但属于 LOCAL_ONLY_RESOURCES，不复制到阿里云。
初始数据由 snh48-fan-hub 的 scripts/data/init_business_tasks.py 从业务清单导入，
之后本页是唯一数据源。
"""
from __future__ import annotations

import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pathlib import Path

from website import config as cfg
from website.maintenance import ensure_writable
from website.rate_limiter import check_admin_login_limit, get_client_ip
from website.shared_runtime_state import (
    SharedStateError,
    SharedStatePeerError,
    execute_mutation,
    load_document,
    register_mutator,
)

router = APIRouter(prefix="/api/business", tags=["应援会业务管理页"])

BJ_TZ = timezone(timedelta(hours=8))
VALID_STATUSES = {"未完成", "已完成"}
TASK_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEXT_LIMIT = 500
BATCH_LIMIT = 500

# 粉丝"记录时昵称 → 最新昵称"映射，由 fan-hub scripts/data/build_fan_name_map.py
# 定期从房间消息生成；文件缺失时静默跳过（显示原名）。
FAN_NAME_MAP_PATH = Path(cfg.BUSINESS_DATA_PATH).resolve().parent / "fan_name_map.json"


def _load_fan_name_map() -> dict[str, Any]:
    try:
        data = json.loads(FAN_NAME_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    mapping = data.get("map")
    return mapping if isinstance(mapping, dict) else {}


# 业务说明参考图：存放在业务数据旁的移交包目录（本地私有，不进 Git、不上阿里云）。
# 按业务类别映射；"?" 弹窗展示，没有映射的类别显示"待添加"。
REFERENCE_DIR = Path(cfg.BUSINESS_DATA_PATH).resolve().parent.parent / "移交包" / "嘉仪业务"
REFERENCE_IMAGES = {
    "暗账": ["总选暗账业务说明.jpg", "总选暗账业务名单.jpg"],
    "积分奖励": ["总选明账业务说明.jpg"],
}
_ALLOWED_REF_NAMES = {name for names in REFERENCE_IMAGES.values() for name in names}
_REF_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

# 说明图 Cookie：<img> 标签无法携带密码请求头，登录成功后种下
# HttpOnly Cookie（值为密码的 HMAC，不存明文），仅对说明图端点有效。
_REF_COOKIE_NAME = "business_ref_token"
_REF_COOKIE_MAX_AGE = 8 * 3600


def _ref_cookie_value() -> str:
    expected = (cfg.BUSINESS_ADMIN_PASSWORD or "").encode("utf-8")
    return hmac.new(expected, b"business-reference-image", digestmod="sha256").hexdigest()


def _verify_ref_access(request: Request) -> None:
    """说明图端点鉴权：密码请求头或登录时种下的 HttpOnly Cookie 二选一。"""
    expected = cfg.BUSINESS_ADMIN_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="应援会业务管理页未启用",
        )
    header_value = request.headers.get("X-Business-Admin-Password")
    if header_value and hmac.compare_digest(expected, header_value):
        return
    cookie = request.cookies.get(_REF_COOKIE_NAME, "")
    if cookie and hmac.compare_digest(_ref_cookie_value(), cookie):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="需要密码",
    )


async def verify_business_password(
    request: Request,
    x_business_admin_password: str = Header(None, alias="X-Business-Admin-Password"),
):
    """Verify the business admin page password."""
    expected = cfg.BUSINESS_ADMIN_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="应援会业务管理页未启用",
        )
    if not x_business_admin_password:
        check_business_login_limit(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要密码",
        )
    if not hmac.compare_digest(expected, x_business_admin_password):
        check_business_login_limit(request)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="密码错误",
        )
    return True


def check_business_login_limit(request: Request) -> None:
    check_admin_login_limit(get_client_ip(request), "业务管理页密码尝试过于频繁，请稍后再试")


def _bj_now() -> str:
    return datetime.now(BJ_TZ).isoformat(timespec="seconds")


def _clean_text(value: Any, limit: int = TEXT_LIMIT) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


@router.get("/verify")
def verify_business_login(
    response: Response,
    _=Depends(verify_business_password),
):
    """Verify the password without loading business data."""
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        _REF_COOKIE_NAME,
        _ref_cookie_value(),
        max_age=_REF_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/business/reference-image",
    )
    return {"verified": True}


@router.get("/data")
def get_business_data(
    response: Response,
    _=Depends(verify_business_password),
):
    """Return every business task grouped by fan on the frontend."""
    response.headers["Cache-Control"] = "no-store"
    try:
        doc = load_document("business_tasks")
    except SharedStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"业务数据读取失败：{exc}",
        ) from exc
    name_map = _load_fan_name_map()
    tasks = [
        _public_task(task, name_map)
        for task in doc.get("tasks", [])
        if isinstance(task, dict)
    ]
    stats = {value: 0 for value in ("未完成", "已完成")}
    for task in tasks:
        stats[task["status"]] = stats.get(task["status"], 0) + 1
    return {
        "generated_at": str(doc.get("generated_at", "")),
        "updated_at": str(doc.get("updated_at", "")),
        "stats": stats,
        "fan_count": len({task["fan_name"] for task in tasks}),
        "tasks": tasks,
    }


def _public_task(task: dict[str, Any], name_map: dict[str, Any] | None = None) -> dict[str, Any]:
    fan_name = _clean_text(task.get("fan_name"), 80)
    latest_name = ""
    if name_map:
        entry = name_map.get(fan_name)
        if isinstance(entry, dict):
            latest_name = _clean_text(entry.get("latest"), 80)
    return {
        "id": _clean_text(task.get("id"), 80),
        "fan_name": fan_name,
        "latest_name": latest_name,
        "biz_type": _clean_text(task.get("biz_type"), 80),
        "category": _clean_text(task.get("category"), 80),
        "status": _normalise_status(task.get("status")),
        "planned_date": _clean_text(task.get("planned_date"), 120),
        "note": _clean_text(task.get("note")),
        "detail": _clean_text(task.get("detail")),
        "source_section": _clean_text(task.get("source_section"), 80),
        "updated_at": _clean_text(task.get("updated_at"), 40),
        "ref_images": list(REFERENCE_IMAGES.get(_clean_text(task.get("category"), 80), [])),
    }


def _normalise_status(value: Any) -> str:
    text = _clean_text(value, 20)
    return text if text in VALID_STATUSES else "未完成"


@router.get("/reference-image")
def get_reference_image(
    request: Request,
    name: str = Query(..., max_length=120),
):
    """按文件名回传业务说明参考图（仅限白名单内的移交包图片）。"""
    _verify_ref_access(request)
    if name not in _ALLOWED_REF_NAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未知说明图")
    path = REFERENCE_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="说明图文件不存在")
    media_type = _REF_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


def _clean_planned_date(value: Any) -> str:
    """planned_date 只接受 ISO 日期或空值。"""
    text = _clean_text(value, 120)
    if not text:
        return ""
    if not ISO_DATE_RE.fullmatch(text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="计划完成时间必须是 YYYY-MM-DD 日期",
        )
    return text


@router.post("/update")
async def update_business_task(
    request: Request,
    _=Depends(verify_business_password),
):
    """Update one task's status/planned_date/note, or add a new task."""
    ensure_writable()
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON 格式无效") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请求体格式无效")

    action = _clean_text(payload.get("action"), 20)
    if action not in {"update", "add", "batch_complete", "set_planned"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效操作")

    try:
        response = execute_mutation("business_tasks", f"business_{action}", payload)
    except SharedStatePeerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except SharedStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"业务数据保存失败：{exc}",
        ) from exc
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    return {
        "ok": True,
        "task": result.get("task") or {},
        "updated_count": int(result.get("updated_count", 0) or 0),
    }


def _update_task_mutator(
    state: dict[str, Any], payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_id = _clean_text(payload.get("id"), 80)
    if not task_id or not re.fullmatch(TASK_ID_RE, task_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="缺少或无效的任务 ID")
    tasks = state.setdefault("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
        state["tasks"] = tasks
    task = next((item for item in tasks if isinstance(item, dict) and item.get("id") == task_id), None)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    if "status" in payload:
        new_status = _normalise_status(payload.get("status"))
        if _clean_text(payload.get("status"), 20) not in VALID_STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效状态")
        task["status"] = new_status
    if "planned_date" in payload:
        task["planned_date"] = _clean_planned_date(payload.get("planned_date"))
    if "note" in payload:
        task["note"] = _clean_text(payload.get("note"))
    task["updated_at"] = _bj_now()
    return state, {"task": _public_task(task)}


def _batch_complete_mutator(
    state: dict[str, Any], payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """把指定 id 列表的任务全部标记为已完成（页面按筛选结果批量操作）。"""
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="缺少任务 ID 列表")
    ids = [_clean_text(item, 80) for item in ids][: BATCH_LIMIT + 1]
    if len(ids) > BATCH_LIMIT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"单次最多批量处理 {BATCH_LIMIT} 条")
    for task_id in ids:
        if not task_id or not re.fullmatch(TASK_ID_RE, task_id):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="存在无效的任务 ID")

    tasks = state.setdefault("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
        state["tasks"] = tasks
    by_id = {item.get("id"): item for item in tasks if isinstance(item, dict)}
    now = _bj_now()
    updated = 0
    for task_id in dict.fromkeys(ids):
        task = by_id.get(task_id)
        if task is None or task.get("status") == "已完成":
            continue
        task["status"] = "已完成"
        task["updated_at"] = now
        updated += 1
    return state, {"updated_count": updated}


def _set_planned_mutator(
    state: dict[str, Any], payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """把指定 id 列表的任务批量设置计划完成时间（页面按粉丝批量设置面取日期）。"""
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="缺少任务 ID 列表")
    ids = [_clean_text(item, 80) for item in ids][: BATCH_LIMIT + 1]
    if len(ids) > BATCH_LIMIT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"单次最多批量处理 {BATCH_LIMIT} 条")
    for task_id in ids:
        if not task_id or not re.fullmatch(TASK_ID_RE, task_id):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="存在无效的任务 ID")
    planned = _clean_planned_date(payload.get("planned_date"))
    if not planned:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择计划完成时间")

    tasks = state.setdefault("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
        state["tasks"] = tasks
    by_id = {item.get("id"): item for item in tasks if isinstance(item, dict)}
    now = _bj_now()
    updated = 0
    for task_id in dict.fromkeys(ids):
        task = by_id.get(task_id)
        if task is None or task.get("status") == "已完成":
            continue
        task["planned_date"] = planned
        task["updated_at"] = now
        updated += 1
    return state, {"updated_count": updated}


def _add_task_mutator(
    state: dict[str, Any], payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    fan_name = _clean_text(payload.get("fan_name"), 80)
    biz_type = _clean_text(payload.get("biz_type"), 80)
    if not fan_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请填写粉丝名称")
    if not biz_type:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请填写业务类型")
    status_value = _clean_text(payload.get("status"), 20) or "未完成"
    if status_value not in VALID_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效状态")

    tasks = state.setdefault("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
        state["tasks"] = tasks
    task = {
        "id": f"bt-web-{uuid.uuid4().hex[:10]}",
        "fan_name": fan_name,
        "biz_type": biz_type,
        "category": _clean_text(payload.get("category"), 80),
        "status": status_value,
        "planned_date": _clean_planned_date(payload.get("planned_date")),
        "note": _clean_text(payload.get("note")),
        "detail": _clean_text(payload.get("detail")),
        "source_section": "网页新增",
        "updated_at": _bj_now(),
    }
    tasks.append(task)
    return state, {"task": _public_task(task)}


register_mutator("business_tasks", "business_update", _update_task_mutator)
register_mutator("business_tasks", "business_add", _add_task_mutator)
register_mutator("business_tasks", "business_batch_complete", _batch_complete_mutator)
register_mutator("business_tasks", "business_set_planned", _set_planned_mutator)

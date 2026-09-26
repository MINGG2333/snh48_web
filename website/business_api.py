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

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

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
VALID_STATUSES = {"待开始", "进行中", "待确认", "已完成"}
TASK_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"
TEXT_LIMIT = 500


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
    tasks = [_public_task(task) for task in doc.get("tasks", []) if isinstance(task, dict)]
    stats = {value: 0 for value in ("待开始", "进行中", "待确认", "已完成")}
    for task in tasks:
        stats[task["status"]] = stats.get(task["status"], 0) + 1
    return {
        "generated_at": str(doc.get("generated_at", "")),
        "updated_at": str(doc.get("updated_at", "")),
        "stats": stats,
        "fan_count": len({task["fan_name"] for task in tasks}),
        "tasks": tasks,
    }


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean_text(task.get("id"), 80),
        "fan_name": _clean_text(task.get("fan_name"), 80),
        "biz_type": _clean_text(task.get("biz_type"), 80),
        "category": _clean_text(task.get("category"), 80),
        "status": _normalise_status(task.get("status")),
        "planned_date": _clean_text(task.get("planned_date"), 120),
        "note": _clean_text(task.get("note")),
        "detail": _clean_text(task.get("detail")),
        "source_section": _clean_text(task.get("source_section"), 80),
        "updated_at": _clean_text(task.get("updated_at"), 40),
    }


def _normalise_status(value: Any) -> str:
    text = _clean_text(value, 20)
    return text if text in VALID_STATUSES else "待开始"


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
    if action not in {"update", "add"}:
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
        task["planned_date"] = _clean_text(payload.get("planned_date"), 120)
    if "note" in payload:
        task["note"] = _clean_text(payload.get("note"))
    task["updated_at"] = _bj_now()
    return state, {"task": _public_task(task)}


def _add_task_mutator(
    state: dict[str, Any], payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    fan_name = _clean_text(payload.get("fan_name"), 80)
    biz_type = _clean_text(payload.get("biz_type"), 80)
    if not fan_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请填写粉丝名称")
    if not biz_type:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请填写业务类型")
    status_value = _clean_text(payload.get("status"), 20) or "待开始"
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
        "planned_date": _clean_text(payload.get("planned_date"), 120),
        "note": _clean_text(payload.get("note")),
        "detail": _clean_text(payload.get("detail")),
        "source_section": "网页新增",
        "updated_at": _bj_now(),
    }
    tasks.append(task)
    return state, {"task": _public_task(task)}


register_mutator("business_tasks", "business_update", _update_task_mutator)
register_mutator("business_tasks", "business_add", _add_task_mutator)

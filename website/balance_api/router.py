"""
FastAPI router that checks the DeepSeek API account balance.

Provides a simple health / balance check endpoint that the frontend
can use to display a status indicator, warning the admin when the
API balance is running low.
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi import Request

from website import config as cfg
from website.rate_limiter import check_balance_limit, get_client_ip

router = APIRouter(prefix="/api/balance", tags=["余额查询"])

DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"

# CHANGED: 余额记录 CSV 路径（带时区）
_BEIJING_TZ = timezone(timedelta(hours=8))
_BALANCE_LOG_DIR = Path(__file__).resolve().parent.parent / "data"
_BALANCE_LOG_CSV = _BALANCE_LOG_DIR / "balance_log.csv"
_BALANCE_CACHE: dict[str, object] = {"expires_at": 0.0, "payload": None}


def _log_balance_record(balance: float, status: str, success: bool, error_msg: str = "") -> None:
    """将一次余额查询结果追加记录到 CSV 文件。"""
    _BALANCE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(_BEIJING_TZ)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    is_new = not _BALANCE_LOG_CSV.exists()
    with open(_BALANCE_LOG_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "balance_cny", "status", "success", "error"])
        writer.writerow([timestamp, f"{balance:.2f}", status, "1" if success else "0", error_msg])


@router.get("")
async def get_balance(request: Request):
    """
    Query DeepSeek API account balance.

    Returns:
      - balance: 当前余额（float，单位 CNY）
      - currency: 币种
      - is_available: 余额是否充足（> 0 元）
      - message: 人类可读的状态描述
    """
    ip = get_client_ip(request)
    check_balance_limit(ip)

    cached = _BALANCE_CACHE.get("payload")
    if cached and time.time() < float(_BALANCE_CACHE.get("expires_at", 0.0)):
        return cached

    # CHANGED: 新增余额查询接口，用于前端显示 API 服务状态
    api_key = cfg.LLM_API_KEY
    if not api_key:
        _log_balance_record(0.0, "exhausted", False, "DEEPSEEK_API_KEY 未配置")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEEPSEEK_API_KEY 未配置",
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                DEEPSEEK_BALANCE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 401:
                _log_balance_record(0.0, "exhausted", False, "API Key 无效或未授权")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API Key 无效或未授权",
                )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        _log_balance_record(0.0, "exhausted", False, "查询余额超时")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="查询 DeepSeek 余额超时",
        )
    except httpx.HTTPError as e:
        _log_balance_record(0.0, "exhausted", False, f"HTTP 错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"查询 DeepSeek 余额失败: {e}",
        )

    # DeepSeek 返回格式：
    # {"is_available": true, "balance_infos": [{"currency": "CNY", "total_balance": "115.50"}]}
    # 注意：total_balance 是字符串，字段名是 total_balance 不是 balance
    # CHANGED: 修复字段名 total_balance（字符串）而非 balance
    # CHANGED: 余额数字只在服务端判断，不返回给前端（隐私保护）
    balance_infos = data.get("balance_infos", [])
    total_balance = 0.0
    if balance_infos:
        for b in balance_infos:
            raw = b.get("total_balance", "0")
            try:
                total_balance += float(raw)
            except (ValueError, TypeError):
                pass

    # 只返回状态级别，不暴露具体余额数字
    if total_balance > 0:
        if total_balance < 10:
            status = "low"       # 余额 < 10 元，黄色预警
        else:
            status = "healthy"   # 余额充足，绿色
    else:
        status = "exhausted"    # 余额耗尽，红色

    # CHANGED: 将本次查询结果记录到 CSV（余额数字只在服务器本地留存）
    _log_balance_record(total_balance, status, True)

    payload = {
        "status": status,
    }
    _BALANCE_CACHE["payload"] = payload
    _BALANCE_CACHE["expires_at"] = time.time() + cfg.BALANCE_CACHE_SECONDS
    return payload

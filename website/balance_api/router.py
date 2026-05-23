"""
FastAPI router that checks the DeepSeek API account balance.

Provides a simple health / balance check endpoint that the frontend
can use to display a status indicator, warning the admin when the
API balance is running low.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, status

from website import config as cfg

router = APIRouter(prefix="/api/balance", tags=["余额查询"])

DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"


@router.get("")
async def get_balance():
    """
    Query DeepSeek API account balance.

    Returns:
      - balance: 当前余额（float，单位 CNY）
      - currency: 币种
      - is_available: 余额是否充足（> 0 元）
      - message: 人类可读的状态描述
    """
    # CHANGED: 新增余额查询接口，用于前端显示 API 服务状态
    api_key = cfg.LLM_API_KEY
    if not api_key:
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
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API Key 无效或未授权",
                )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="查询 DeepSeek 余额超时",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"查询 DeepSeek 余额失败: {e}",
        )

    # DeepSeek 返回格式：{"is_available": true, "balance_infos": [{"balance": 123.45, "currency": "CNY"}]}
    balance_infos = data.get("balance_infos", [])
    total_balance = sum(b.get("balance", 0) for b in balance_infos) if balance_infos else 0

    is_available = data.get("is_available", False)
    return {
        "balance": total_balance,
        "currency": balance_infos[0].get("currency", "CNY") if balance_infos else "CNY",
        "is_available": is_available,
        "message": f"余额充足（￥{total_balance:.2f}）" if is_available and total_balance > 0
                   else "余额不足，请及时充值" if total_balance <= 0
                   else "服务异常，请检查 API 状态",
    }

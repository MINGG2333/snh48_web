"""Password-protected API for the small room score-PK dataset."""
from __future__ import annotations

import hmac
import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from website import config as cfg
from website.rate_limiter import check_admin_login_limit, get_client_ip


router = APIRouter(prefix="/api/pk-score", tags=["房间计分 PK"])
_cache_lock = threading.Lock()
_cache_mtime_ns = -1
_cache_doc: dict[str, Any] = {}


def check_pk_score_login_limit(request: Request) -> None:
    check_admin_login_limit(get_client_ip(request), "房间计分 PK 页面密码尝试过于频繁，请稍后再试")


async def verify_pk_score_password(
    request: Request,
    x_pk_score_password: str = Header(None, alias="X-PK-Score-Password"),
):
    expected = cfg.PK_SCORE_PASSWORD
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="房间计分 PK 页面未启用")
    if not x_pk_score_password:
        check_pk_score_login_limit(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要密码")
    if not hmac.compare_digest(expected, x_pk_score_password):
        check_pk_score_login_limit(request)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    return True


@router.get("/verify")
def verify_pk_score_login(response: Response, _=Depends(verify_pk_score_password)):
    response.headers["Cache-Control"] = "no-store"
    return {"verified": True}


@router.get("/data")
async def get_pk_score_data(response: Response, _=Depends(verify_pk_score_password)):
    response.headers["Cache-Control"] = "no-store"
    return _load_dataset()


def _data_path() -> Path:
    return Path(cfg.PK_SCORE_DATA_PATH)


def _load_dataset() -> dict[str, Any]:
    global _cache_doc, _cache_mtime_ns
    path = _data_path()
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PK 计分数据尚未生成") from exc

    with _cache_lock:
        if _cache_doc and _cache_mtime_ns == mtime_ns:
            return _cache_doc
        try:
            with path.open("r", encoding="utf-8") as handle:
                doc = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PK 计分数据读取失败") from exc
        _validate_dataset(doc)
        _cache_doc = doc
        _cache_mtime_ns = mtime_ns
        return doc


def _validate_dataset(doc: Any) -> None:
    if not isinstance(doc, dict) or int(doc.get("version") or 0) != 1:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PK 计分数据版本无效")
    competitors = doc.get("competitors")
    items = doc.get("items")
    if not isinstance(competitors, list) or len(competitors) != 2 or not isinstance(items, list):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PK 计分数据结构无效")

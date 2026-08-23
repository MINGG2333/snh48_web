"""Password-protected API for validating and replacing social cookies."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import signal
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from website import config as cfg
from website.rate_limiter import check_admin_login_limit, get_client_ip


router = APIRouter(prefix="/api/social-credentials", tags=["社交凭据管理"])
AUTH_COOKIE = "social_credentials_auth"
AUTH_COOKIE_MAX_AGE = 30 * 60
_COOKIE_SECRET = os.urandom(32)
PLATFORMS = {"weibo", "douyin", "bilibili"}
SLOTS = {"primary", "backup"}


class LoginRequest(BaseModel):
    password: str


class UpdateRequest(BaseModel):
    platform: str
    slot: str
    cookie: str


def _token(password: str) -> str:
    return hashlib.sha256(_COOKIE_SECRET + password.encode("utf-8")).hexdigest()


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


def _require_enabled() -> None:
    if not cfg.SOCIAL_CREDENTIALS_ADMIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前节点未启用凭据管理")


def _same_origin(request: Request) -> None:
    origin = str(request.headers.get("origin") or "").strip()
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host", ""):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请求来源无效")


def _run_bridge(command: str, payload: dict) -> dict:
    script = Path(cfg.SOCIAL_CREDENTIALS_ADMIN_SCRIPT)
    if not script.is_file():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="凭据管理桥未就绪")
    proc = None
    try:
        proc = subprocess.Popen(
            [cfg.SOCIAL_CREDENTIALS_ADMIN_PYTHON, str(script), command],
            cwd=script.parents[2],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        stdout, _ = proc.communicate(json.dumps(payload, ensure_ascii=False), timeout=180)
        result = json.loads((stdout or "").strip())
    except subprocess.TimeoutExpired:
        assert proc is not None
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Cookie 验证超时，原配置未更改")
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="凭据管理桥暂时不可用")
    if not isinstance(result, dict):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="凭据管理桥返回异常")
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(result.get("error") or "验证失败"))
    return result


async def require_auth(request: Request, social_credentials_auth: str = Cookie(None, alias=AUTH_COOKIE)):
    _require_enabled()
    expected = cfg.SOCIAL_CREDENTIALS_ADMIN_PASSWORD
    if social_credentials_auth and hmac.compare_digest(social_credentials_auth, _token(expected)):
        return True
    if not social_credentials_auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要密码")
    check_admin_login_limit(get_client_ip(request), "社交凭据管理认证失败次数过多，请稍后再试")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="登录状态无效")


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    _require_enabled()
    if not hmac.compare_digest(payload.password, cfg.SOCIAL_CREDENTIALS_ADMIN_PASSWORD):
        check_admin_login_limit(get_client_ip(request), "社交凭据管理密码尝试过于频繁，请稍后再试")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    response.set_cookie(
        AUTH_COOKIE,
        _token(cfg.SOCIAL_CREDENTIALS_ADMIN_PASSWORD),
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
        path="/api/social-credentials",
    )
    _no_store(response)
    return {"success": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        AUTH_COOKIE,
        path="/api/social-credentials",
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
    )
    _no_store(response)
    return {"success": True}


@router.get("/status")
async def credential_status(response: Response, _=Depends(require_auth)):
    _no_store(response)
    return await asyncio.to_thread(_run_bridge, "status", {})


@router.post("/update")
async def update_credential(payload: UpdateRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    platform = payload.platform.strip().lower()
    slot = payload.slot.strip().lower()
    cookie = payload.cookie.strip()
    if platform not in PLATFORMS or slot not in SLOTS or (platform == "bilibili" and slot != "primary"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="平台或 Cookie 槽位无效")
    if len(cookie) < 20 or len(cookie) > 65536 or "\n" in cookie or "\r" in cookie:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cookie 必须是单行完整文本")
    _no_store(response)
    return await asyncio.to_thread(
        _run_bridge,
        "update",
        {"platform": platform, "slot": slot, "cookie": cookie},
    )

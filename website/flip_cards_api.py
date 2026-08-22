"""Password-protected Pocket48 flip-card app data and media API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import subprocess
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from website import config as cfg
from website.rate_limiter import check_admin_login_limit, get_client_ip


router = APIRouter(prefix="/api/flip-cards", tags=["翻牌记录页"])

AUTH_COOKIE = "flip_cards_auth"
AUTH_COOKIE_MAX_AGE = 24 * 60 * 60
_COOKIE_SECRET = os.urandom(32)
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
MEDIA_TYPES = {
    "audio": {
        "suffix": ".mp3",
        "media_type": "audio/mpeg",
        "missing": "翻牌语音不存在",
    },
    "video": {
        "suffix": ".mp4",
        "media_type": "video/mp4",
        "missing": "翻牌视频不存在",
    },
}


class LoginRequest(BaseModel):
    password: str


class SmsRequest(BaseModel):
    phone: str
    area: str = "86"


class SecurityAnswerRequest(BaseModel):
    session_id: str
    option: str


class VerifyCodeRequest(BaseModel):
    session_id: str
    code: str


def _cookie_token(password: str) -> str:
    return hashlib.sha256(_COOKIE_SECRET + password.encode("utf-8")).hexdigest()


def _expected_password() -> str:
    return cfg.FLIP_CARDS_PASSWORD


def _data_dir() -> Path:
    return Path(cfg.FLIP_CARDS_DATA_DIR)


def _dataset_path() -> Path:
    return Path(cfg.FLIP_CARDS_DATASET_PATH)


def _accounts_path() -> Path:
    return Path(cfg.FLIP_CARDS_ACCOUNTS_PATH)


def _load_json_object(path: Path, missing_detail: str) -> dict:
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_detail)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="翻牌应用数据读取失败")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="翻牌应用数据格式错误")
    return payload


def _load_accounts_manifest(*, allow_legacy: bool = True) -> dict:
    path = _accounts_path()
    if path.is_file():
        payload = _load_json_object(path, "翻牌账号清单尚未生成")
        accounts = payload.get("accounts")
        if not isinstance(accounts, list):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="翻牌账号清单格式错误")
        return payload
    if allow_legacy and _dataset_path().is_file():
        return {"schema_version": 0, "default_account_id": "", "accounts": []}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌账号清单尚未生成")


def _safe_account_id(value: str) -> str:
    account_id = str(value or "").strip()
    if not re.fullmatch(r"\d{5,20}", account_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌账号不存在")
    return account_id


def _account_ids(manifest: dict) -> set[str]:
    return {
        str(item.get("id") or "")
        for item in manifest.get("accounts", [])
        if isinstance(item, dict) and str(item.get("id") or "").isdigit()
    }


def _resolve_dataset(account_id: str = "") -> tuple[Path, str]:
    manifest = _load_accounts_manifest()
    if not manifest.get("accounts"):
        if account_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌账号不存在")
        return _dataset_path(), ""
    selected = _safe_account_id(account_id or str(manifest.get("default_account_id") or ""))
    if selected not in _account_ids(manifest):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌账号不存在")
    return _data_dir() / "web" / "accounts" / f"{selected}.json", selected


def _require_same_origin(request: Request) -> None:
    origin = str(request.headers.get("origin") or "").strip()
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host", ""):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请求来源无效")


def _require_account_admin(request: Request) -> None:
    if not cfg.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前节点不开放账号操作")
    _require_same_origin(request)


def _run_account_admin(command: str, payload: dict) -> dict:
    script_path = Path(cfg.FLIP_CARDS_ACCOUNT_ADMIN_SCRIPT)
    if not script_path.is_file():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="账号管理服务未就绪")
    try:
        proc = subprocess.run(
            [cfg.FLIP_CARDS_ACCOUNT_ADMIN_PYTHON, str(script_path), command],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
            cwd=script_path.parents[2],
        )
        result = json.loads((proc.stdout or "").strip())
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="账号管理服务暂时不可用")
    if not isinstance(result, dict):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="账号管理服务返回异常")
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(result.get("error") or "账号操作失败"))
    return result


async def verify_flip_cards_auth(
    request: Request,
    x_flip_cards_password: str = Header(None, alias="X-Flip-Cards-Password"),
    flip_cards_auth: str = Cookie(None, alias=AUTH_COOKIE),
):
    expected = _expected_password()
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="翻牌记录页未启用")
    if flip_cards_auth and hmac.compare_digest(flip_cards_auth, _cookie_token(expected)):
        return True
    if x_flip_cards_password and hmac.compare_digest(x_flip_cards_password, expected):
        return True
    if not flip_cards_auth and not x_flip_cards_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要密码")
    check_admin_login_limit(get_client_ip(request), "翻牌记录页密码尝试过于频繁，请稍后再试")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")


@router.post("/login")
async def login(payload: LoginRequest, response: Response, request: Request):
    expected = _expected_password()
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="翻牌记录页未启用")
    if not hmac.compare_digest(payload.password, expected):
        check_admin_login_limit(get_client_ip(request), "翻牌记录页密码尝试过于频繁，请稍后再试")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    response.set_cookie(
        key=AUTH_COOKIE,
        value=_cookie_token(expected),
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
        path="/api/flip-cards",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        key=AUTH_COOKIE,
        path="/api/flip-cards",
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}


@router.get("/status")
async def auth_status(response: Response, _=Depends(verify_flip_cards_auth)):
    dataset_path = _dataset_path()
    response.headers["Cache-Control"] = "no-store"
    return {
        "success": True,
        "dataset_exists": dataset_path.is_file(),
        "dataset_mtime": int(dataset_path.stat().st_mtime) if dataset_path.is_file() else 0,
    }


@router.get("/accounts")
async def flip_card_accounts(response: Response, _=Depends(verify_flip_cards_auth)):
    manifest = _load_accounts_manifest()
    response.headers["Cache-Control"] = "private, no-store"
    return manifest


@router.get("/account-management/status")
async def account_management_status(response: Response, _=Depends(verify_flip_cards_auth)):
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "enabled": bool(cfg.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED),
        "message": "" if cfg.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED else "当前节点不开放账号操作",
    }


@router.post("/account-management/send-sms")
async def account_management_send_sms(payload: SmsRequest, request: Request, response: Response, _=Depends(verify_flip_cards_auth)):
    _require_account_admin(request)
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(_run_account_admin, "send-sms", {"phone": payload.phone, "area": payload.area})


@router.post("/account-management/security-answer")
async def account_management_security_answer(payload: SecurityAnswerRequest, request: Request, response: Response, _=Depends(verify_flip_cards_auth)):
    _require_account_admin(request)
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(_run_account_admin, "security-answer", {"session_id": payload.session_id, "option": payload.option})


@router.post("/account-management/verify-code")
async def account_management_verify_code(payload: VerifyCodeRequest, request: Request, response: Response, _=Depends(verify_flip_cards_auth)):
    _require_account_admin(request)
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(_run_account_admin, "verify-code", {"session_id": payload.session_id, "code": payload.code})


@router.get("/account-management/jobs/{job_id}")
async def account_management_job(job_id: str, request: Request, response: Response, _=Depends(verify_flip_cards_auth)):
    if not cfg.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前节点不开放账号操作")
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(_run_account_admin, "job-status", {"job_id": job_id})


@router.get("/data")
async def flip_cards_data(response: Response, account_id: str = "", _=Depends(verify_flip_cards_auth)):
    dataset_path, selected_account_id = _resolve_dataset(account_id)
    payload = _load_json_object(dataset_path, "翻牌应用数据尚未生成")

    records = payload.get("records")
    if not isinstance(records, list):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="翻牌应用数据格式错误")
    for record in records:
        if not isinstance(record, dict):
            continue
        media = record.get("media")
        if not isinstance(media, dict):
            continue
        kind = str(media.get("kind") or "")
        filename = str(media.get("filename") or "")
        if kind in MEDIA_TYPES and filename:
            if selected_account_id:
                media["url"] = f"/api/flip-cards/accounts/{selected_account_id}/flip_data/{kind}/{quote(filename)}"
            else:
                media["url"] = f"/api/flip-cards/flip_data/{kind}/{quote(filename)}"

    response.headers["Cache-Control"] = "private, no-store"
    return payload


def _safe_media_filename(filename: str, kind: str) -> str:
    value = str(filename or "").strip()
    info = MEDIA_TYPES.get(kind)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌媒体不存在")
    if not value or Path(value).name != value or "\x00" in value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=info["missing"])
    if not value.lower().endswith(str(info["suffix"])):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=info["missing"])
    return value


def _parse_range(value: str, size: int) -> tuple[int, int, bool]:
    if not value:
        return 0, max(0, size - 1), False
    match = RANGE_RE.fullmatch(value.strip())
    if not match or size <= 0:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="无效的媒体范围",
            headers={"Content-Range": f"bytes */{size}"},
        )
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="无效的媒体范围",
            headers={"Content-Range": f"bytes */{size}"},
        )
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="无效的媒体范围",
                headers={"Content-Range": f"bytes */{size}"},
            )
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    if start >= size or start < 0 or end < start:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="无效的媒体范围",
            headers={"Content-Range": f"bytes */{size}"},
        )
    return start, min(end, size - 1), True


async def _file_iterator(path: Path, start: int, length: int) -> AsyncIterator[bytes]:
    remaining = length
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(64 * 1024, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk


@router.get("/flip_data/{kind}/{filename}")
async def stream_media(
    request: Request,
    kind: str,
    filename: str,
    _=Depends(verify_flip_cards_auth),
):
    info = MEDIA_TYPES.get(kind)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌媒体不存在")
    safe_filename = _safe_media_filename(filename, kind)
    media_dir = (_data_dir() / kind).resolve()
    path = (media_dir / safe_filename).resolve()
    if path.parent != media_dir or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=info["missing"])
    size = path.stat().st_size
    start, end, partial = _parse_range(request.headers.get("range", ""), size)
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _file_iterator(path, start, length),
        status_code=status.HTTP_206_PARTIAL_CONTENT if partial else status.HTTP_200_OK,
        media_type=str(info["media_type"]),
        headers=headers,
    )


@router.get("/accounts/{account_id}/flip_data/{kind}/{filename}")
async def stream_account_media(
    request: Request,
    account_id: str,
    kind: str,
    filename: str,
    _=Depends(verify_flip_cards_auth),
):
    manifest = _load_accounts_manifest(allow_legacy=False)
    selected = _safe_account_id(account_id)
    if selected not in _account_ids(manifest):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌账号不存在")
    info = MEDIA_TYPES.get(kind)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌媒体不存在")
    safe_filename = _safe_media_filename(filename, kind)
    media_dir = (_data_dir() / kind / selected).resolve()
    path = (media_dir / safe_filename).resolve()
    if path.parent != media_dir or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=info["missing"])
    size = path.stat().st_size
    start, end, partial = _parse_range(request.headers.get("range", ""), size)
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _file_iterator(path, start, length),
        status_code=status.HTTP_206_PARTIAL_CONTENT if partial else status.HTTP_200_OK,
        media_type=str(info["media_type"]),
        headers=headers,
    )

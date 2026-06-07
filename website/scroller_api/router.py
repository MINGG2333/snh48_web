"""
FastAPI router for managing scroller background texts.

Provides endpoints to:
- GET  /api/scroller/texts   – retrieve the list of scrolling texts (public)
- POST /api/scroller/login   – verify password, set HttpOnly cookie
- POST /api/scroller/logout  – clear auth cookie
- PUT  /api/scroller/texts   – update the list of scrolling texts (cookie-protected)

Uses SCROLLER_PASSWORD (independent from the QA password SITE_PASSWORD).
Set via environment variable or .env file:
    SCROLLER_PASSWORD=your_scroller_password

Auth uses HttpOnly cookie (not sessionStorage) to prevent JS-based theft.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Cookie, Depends, HTTPException, Header, Request, Response, status
from pydantic import BaseModel

from website import config as cfg
from website.rate_limiter import check_scroller_login_limit, get_client_ip

# ── Cookie name for scroller auth ────────────────────────────────────────
SCROLLER_COOKIE = "scroller_auth"
SCROLLER_COOKIE_MAX_AGE = 3600 * 24  # 24 hours

# Server-side secret for HMAC-based cookie token (changes on restart).
# Cookie stores hash, never the raw password.
_COOKIE_SECRET = os.urandom(32)


def _make_cookie_token(password: str) -> str:
    """Create a hashed token from password + server secret for cookie storage."""
    return hashlib.sha256(_COOKIE_SECRET + password.encode()).hexdigest()


def _verify_cookie_token(token: str, password: str) -> bool:
    """Constant-time compare cookie token against expected password hash."""
    return hmac.compare_digest(_make_cookie_token(password), token)

# ── Data file path ───────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEXTS_FILE = DATA_DIR / "scroller_texts.json"


def _load_texts() -> List[str]:
    """Load texts from the JSON data file."""
    if not TEXTS_FILE.exists():
        return []
    try:
        with open(TEXTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and all(isinstance(t, str) for t in data):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _save_texts(texts: List[str]) -> None:
    """Save texts to the JSON data file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEXTS_FILE, "w", encoding="utf-8") as f:
        json.dump(texts, f, ensure_ascii=False, indent=2)


router = APIRouter(prefix="/api/scroller", tags=["背景词管理"])


# ── Request / Response Models ──────────────────────────────────────────────


class TextsResponse(BaseModel):
    texts: List[str]
    count: int


class TextsUpdateRequest(BaseModel):
    texts: List[str]


# ── Public: GET /api/scroller/texts ─────────────────────────────────────────


@router.get("/texts", response_model=TextsResponse)
def get_texts():
    """
    Public endpoint – retrieve the list of scrolling background texts.
    No authentication required (these are just display texts).
    """
    texts = _load_texts()
    return TextsResponse(texts=texts, count=len(texts))


# ── Independent password auth for scroller (cookie + header fallback) ────


async def verify_scroller_auth(
    x_scroller_password: str = Header(None, alias="X-Scroller-Password"),
    scroller_auth: str = Cookie(None, alias=SCROLLER_COOKIE),
):
    """
    FastAPI dependency: verify scroller admin access via HttpOnly cookie or header.

    Priority: HttpOnly cookie first, then X-Scroller-Password header (legacy fallback).
    If SCROLLER_PASSWORD is not set, the feature is disabled.
    """
    expected = cfg.SCROLLER_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="背景词管理功能未启用。请通知管理员设置以启用此功能。",
        )

    # Check HttpOnly cookie first (primary auth method — stores hash, not password)
    if scroller_auth and _verify_cookie_token(scroller_auth, expected):
        return True

    # Fallback: check header (legacy, for backward compatibility)
    if x_scroller_password and hmac.compare_digest(expected, x_scroller_password):
        return True

    if not scroller_auth and not x_scroller_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要背景词管理密码才能访问。请先登录。",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="背景词管理密码错误，拒绝访问。",
    )


# ── Login endpoint (sets HttpOnly cookie) ────────────────────────────────


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def scroller_login(req: LoginRequest, response: Response, request: Request):
    """
    Verify scroller admin password and set an HttpOnly cookie.
    The cookie cannot be read by JavaScript, preventing XSS-based theft.
    """
    # Rate-limit login attempts to prevent brute-force
    ip = get_client_ip(request)
    check_scroller_login_limit(ip)

    expected = cfg.SCROLLER_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="背景词管理功能未启用。请通知管理员设置以启用此功能。",
        )

    if not hmac.compare_digest(expected, req.password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="密码错误",
        )

    response.set_cookie(
        key=SCROLLER_COOKIE,
        value=_make_cookie_token(expected),   # HMAC hash, NOT the raw password
        max_age=SCROLLER_COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=False,  # Set to True if behind HTTPS
        path="/api/scroller",
    )
    return {"success": True, "message": "登录成功"}


# ── Logout endpoint (clears cookie) ──────────────────────────────────────


@router.post("/logout")
def scroller_logout(response: Response):
    """Clear the scroller auth cookie (logout)."""
    response.delete_cookie(
        key=SCROLLER_COOKIE,
        path="/api/scroller",
        httponly=True,
        samesite="strict",
    )
    return {"success": True, "message": "已登出"}


# ── Protected: PUT /api/scroller/texts ─────────────────────────────────────


@router.put("/texts", response_model=TextsResponse)
def update_texts(req: TextsUpdateRequest, _=Depends(verify_scroller_auth)):
    """
    Cookie-protected endpoint – replace the list of scrolling texts.
    Authentication via HttpOnly cookie (set by POST /api/scroller/login).
    """
    texts = req.texts
    cleaned = [t.strip() for t in texts if t.strip()]
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="列表不能为空，至少需要一条背景词",
        )

    _save_texts(cleaned)
    return TextsResponse(texts=cleaned, count=len(cleaned))

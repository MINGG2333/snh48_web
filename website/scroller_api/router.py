"""
FastAPI router for managing scroller background texts.

Provides endpoints to:
- GET  /api/scroller/texts   – retrieve the list of scrolling texts (public)
- PUT  /api/scroller/texts   – update the list of scrolling texts (password-protected)

Uses SCROLLER_PASSWORD (independent from the QA password SITE_PASSWORD).
Set via environment variable or .env file:
    SCROLLER_PASSWORD=your_scroller_password
"""
from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, Header, Depends, HTTPException, status
from pydantic import BaseModel

from website import config as cfg

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


# ── Independent password auth for scroller ────────────────────────────────


async def verify_scroller_password(x_scroller_password: str = Header(None, alias="X-Scroller-Password")):
    """
    FastAPI dependency: verify the scroller admin password from request header.
    Uses SCROLLER_PASSWORD (independent from SITE_PASSWORD).
    If SCROLLER_PASSWORD is not set, the feature is disabled.
    """
    expected = cfg.SCROLLER_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="背景词管理功能未启用。请在 .env 中设置 SCROLLER_PASSWORD 以启用此功能。",
        )

    if not x_scroller_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要背景词管理密码才能访问。请在请求头中携带 X-Scroller-Password。",
        )

    if not hmac.compare_digest(expected, x_scroller_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="背景词管理密码错误，拒绝访问。",
        )

    return True


# ── Protected: PUT /api/scroller/texts ─────────────────────────────────────


@router.put("/texts", response_model=TextsResponse)
def update_texts(req: TextsUpdateRequest, _=Depends(verify_scroller_password)):
    """
    Password-protected endpoint – replace the list of scrolling texts.
    Requires X-Scroller-Password header (independent from SITE_PASSWORD).
    """
    texts = req.texts
    # Basic validation: ensure all items are non-empty strings
    cleaned = [t.strip() for t in texts if t.strip()]
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="列表不能为空，至少需要一条背景词",
        )

    _save_texts(cleaned)
    return TextsResponse(texts=cleaned, count=len(cleaned))

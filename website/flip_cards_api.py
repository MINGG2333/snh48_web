"""Password-protected Pocket48 flip-card HTML and media API."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
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


def _cookie_token(password: str) -> str:
    return hashlib.sha256(_COOKIE_SECRET + password.encode("utf-8")).hexdigest()


def _expected_password() -> str:
    return cfg.FLIP_CARDS_PASSWORD


def _html_path() -> Path:
    return Path(cfg.FLIP_CARDS_HTML_PATH)


def _data_dir() -> Path:
    return Path(cfg.FLIP_CARDS_DATA_DIR)


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
    html_path = _html_path()
    response.headers["Cache-Control"] = "no-store"
    return {
        "success": True,
        "html_exists": html_path.is_file(),
        "html_mtime": int(html_path.stat().st_mtime) if html_path.is_file() else 0,
    }


@router.get("/html", response_class=HTMLResponse)
async def flip_cards_html(response: Response, _=Depends(verify_flip_cards_auth)):
    html_path = _html_path()
    if not html_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="翻牌 HTML 尚未生成")
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="翻牌 HTML 读取失败")
    response.headers["Cache-Control"] = "private, no-store"
    return HTMLResponse(_prepare_html(html), headers={"Cache-Control": "private, no-store"})


def _prepare_html(html: str) -> str:
    lower = html.lower()
    head_insert = (
        '<base href="/api/flip-cards/">\n'
        '<meta name="robots" content="noindex,nofollow">\n'
    )
    if "<base " not in lower and "<meta name=\"robots\"" not in lower:
        html = html.replace("<head>", f"<head>\n{head_insert}", 1)
    elif "<base " not in lower:
        html = html.replace("<head>", '<head>\n<base href="/api/flip-cards/">', 1)
    elif "<meta name=\"robots\"" not in lower:
        html = html.replace("<head>", '<head>\n<meta name="robots" content="noindex,nofollow">', 1)

    toolbar = """
<div id="flipCardsOnlineBar">
  <button id="flipCardsLogout" type="button">退出</button>
</div>
<style>
#flipCardsOnlineBar {
  position: fixed; right: 14px; bottom: 14px; z-index: 10000;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
#flipCardsOnlineBar button {
  min-width: 64px; min-height: 36px; border: 1px solid rgba(0,0,0,.12);
  border-radius: 8px; background: rgba(255,255,255,.96); color: #333;
  box-shadow: 0 8px 24px rgba(0,0,0,.14); cursor: pointer;
}
</style>
<script src="/static/js/tracker.js"></script>
<script>
(function () {
  function track(eventType, data) {
    if (!window._trackEvent) return;
    window._trackEvent(eventType, Object.assign({ area: "flip_cards" }, data || {}));
  }
  track("admin_modal", { action: "view_flip_cards_html" });
  var logout = document.getElementById("flipCardsLogout");
  if (logout) {
    logout.addEventListener("click", function () {
      track("login_attempt", { action: "logout", result: "submitted" });
      fetch("/api/flip-cards/logout", { method: "POST", credentials: "same-origin" })
        .finally(function () { window.location.href = "/flip-cards"; });
    });
  }
}());
</script>
"""
    if "</body>" in lower:
        return html.replace("</body>", toolbar + "\n</body>", 1)
    return html + toolbar


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

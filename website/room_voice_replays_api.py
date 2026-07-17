"""Password-protected Pocket48 member-room voice replay API."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from website import config as cfg
from website.rate_limiter import check_admin_login_limit, get_client_ip


router = APIRouter(prefix="/api/room-voice-replays", tags=["房间上麦回放"])

AUTH_COOKIE = "room_voice_replays_auth"
AUTH_COOKIE_MAX_AGE = 24 * 60 * 60
_COOKIE_SECRET = os.urandom(32)
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
SEGMENT_NAME_RE = re.compile(r"^segment_[0-9]{6}\.m4a$")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


class LoginRequest(BaseModel):
    password: str


def _cookie_token(password: str) -> str:
    return hashlib.sha256(_COOKIE_SECRET + password.encode("utf-8")).hexdigest()


def _root() -> Path:
    return Path(cfg.ROOM_VOICE_REPLAYS_DIR)


def _safe_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not SESSION_ID_RE.fullmatch(value):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回放不存在")
    return value


def _safe_segment_name(filename: str) -> str:
    value = str(filename or "").strip()
    if not SEGMENT_NAME_RE.fullmatch(value):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="音频分段不存在")
    return value


def _read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


async def verify_room_voice_replays_auth(
    request: Request,
    x_room_voice_replays_password: str = Header(None, alias="X-Room-Voice-Replays-Password"),
    room_voice_replays_auth: str = Cookie(None, alias=AUTH_COOKIE),
):
    expected = cfg.ROOM_VOICE_REPLAYS_PASSWORD
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="房间上麦回放未启用")
    if room_voice_replays_auth and hmac.compare_digest(
        room_voice_replays_auth, _cookie_token(expected)
    ):
        return True
    if x_room_voice_replays_password and hmac.compare_digest(
        x_room_voice_replays_password, expected
    ):
        return True
    if not room_voice_replays_auth and not x_room_voice_replays_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要密码")
    check_admin_login_limit(
        get_client_ip(request), "房间上麦回放密码尝试过于频繁，请稍后再试"
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")


@router.post("/login")
async def login(payload: LoginRequest, response: Response, request: Request):
    expected = cfg.ROOM_VOICE_REPLAYS_PASSWORD
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="房间上麦回放未启用")
    if not hmac.compare_digest(payload.password, expected):
        check_admin_login_limit(
            get_client_ip(request), "房间上麦回放密码尝试过于频繁，请稍后再试"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    response.set_cookie(
        key=AUTH_COOKIE,
        value=_cookie_token(expected),
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
        path="/api/room-voice-replays",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        key=AUTH_COOKIE,
        path="/api/room-voice-replays",
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}


@router.get("/sessions")
async def list_sessions(response: Response, _=Depends(verify_room_voice_replays_auth)):
    manifest = _read_json(_root() / "manifest.json", {})
    sessions = manifest.get("sessions", []) if isinstance(manifest, dict) else []
    response.headers["Cache-Control"] = "no-store"
    return {
        "schema_version": manifest.get("schema_version", 1) if isinstance(manifest, dict) else 1,
        "generated_at_bj": manifest.get("generated_at_bj", "") if isinstance(manifest, dict) else "",
        "sessions": [item for item in sessions if isinstance(item, dict)],
    }


@router.get("/sessions/{session_id}")
async def session_detail(
    session_id: str,
    response: Response,
    _=Depends(verify_room_voice_replays_auth),
):
    safe_id = _safe_session_id(session_id)
    session_dir = _root() / "sessions" / safe_id
    session = _read_json(session_dir / "session.json", {})
    if not isinstance(session, dict) or session.get("session_id") != safe_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回放不存在")
    segments = []
    for item in session.get("segments", []):
        if not isinstance(item, dict):
            continue
        filename = Path(str(item.get("filename") or "")).name
        if not SEGMENT_NAME_RE.fullmatch(filename):
            continue
        segments.append(
            {
                **item,
                "media_url": f"/api/room-voice-replays/sessions/{safe_id}/segments/{filename}",
            }
        )
    messages = _read_jsonl(session_dir / "messages.jsonl")
    response.headers["Cache-Control"] = "no-store"
    return {"session": {**session, "segments": segments}, "messages": messages}


def _parse_range(value: str, size: int) -> tuple[int, int, bool]:
    if not value:
        return 0, max(0, size - 1), False
    match = RANGE_RE.fullmatch(value.strip())
    if not match or size <= 0:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="无效的音频范围",
            headers={"Content-Range": f"bytes */{size}"},
        )
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="无效的音频范围",
            headers={"Content-Range": f"bytes */{size}"},
        )
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="无效的音频范围",
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
            detail="无效的音频范围",
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


@router.get("/sessions/{session_id}/segments/{filename}")
async def stream_segment(
    request: Request,
    session_id: str,
    filename: str,
    _=Depends(verify_room_voice_replays_auth),
):
    safe_id = _safe_session_id(session_id)
    safe_filename = _safe_segment_name(filename)
    segment_dir = (_root() / "sessions" / safe_id / "segments").resolve()
    path = (segment_dir / safe_filename).resolve()
    if path.parent != segment_dir or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="音频分段不存在")
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
        media_type="audio/mp4",
        headers=headers,
    )

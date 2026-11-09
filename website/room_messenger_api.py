"""Room messenger API: personal-account Pocket48 room message sending.

The page is a private, Tencent-only admin tool.  The Pocket48 personal Token
never enters this process: login, history reads and QChat sends are proxied to
the local root bridge (``snh48-privileged-bridge-flip.service``), which owns the
account database.  Scheduled jobs and audit state live in
``/var/lib/snh48-web/room_messenger`` and contain no Tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import random
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from website import config as cfg
from website import password_session
from website.rate_limiter import check_admin_login_limit, get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/room-messenger", tags=["房间消息发送"])
AUTH_COOKIE = "room_messenger_auth"
AUTH_COOKIE_MAX_AGE = password_session.cookie_max_age()
TZ = timezone(timedelta(hours=8))
SEND_CONFIRM_WORD = "确认发送"
MAX_TEXT_LENGTH = 1000
MAX_CATALOG_PAGE = 100
MAX_RECENT_CHANNELS = 30
MAX_JOB_HISTORY = 100
BRIDGE_TIMEOUT_SECONDS = 400
ACCOUNT_ID_RE = re.compile(r"^\d{1,32}$")
CHANNEL_ID_RE = re.compile(r"^\d{1,32}$")
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_GROUP_ORDER = {
    "SNH48": 0,
    "GNZ48": 1,
    "BEJ48": 2,
    "CKG48": 3,
    "SHY48": 4,
    "CGT48": 5,
    "IDFT": 6,
}

_state_lock = threading.RLock()
_scheduler_started = False
_scheduler_recovered = False
_catalog_lock = threading.Lock()
_catalog_cache: tuple[Any, list[dict[str, Any]]] | None = None


# ── Small utilities ───────────────────────────────────────────────────────


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


def _require_enabled() -> None:
    if not cfg.ROOM_MESSENGER_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="消息发送页仅腾讯云私密站启用")


def _state_dir() -> Path:
    root = Path(getattr(cfg, "ROOM_MESSENGER_STATE_DIR", "/var/lib/snh48-web/room_messenger"))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _state_path(name: str) -> Path:
    return _state_dir() / name


def _read_json(path: Path, default: Any) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return data if isinstance(data, type(default)) else default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _safe_error(value: Any, fallback: str = "操作失败") -> str:
    text = " ".join(str(value or fallback).split())[:300]
    return re.sub(r"(?<!\d)\d{7,}(?!\d)", "[已隐藏]", text)


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    text = raw.strip()
    if not (text.startswith("{") or text.startswith("[")):
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _message_preview(text: str, limit: int = 60) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit]


# ── Bridge ────────────────────────────────────────────────────────────────


class BridgeError(RuntimeError):
    """Bridge request failed for a user-visible reason."""


class BridgeUnavailable(RuntimeError):
    """Bridge is missing, timed out or returned malformed output."""


def _run_bridge(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    prefix = tuple(getattr(cfg, "ROOM_MESSENGER_COMMAND", ()) or ())
    script = Path(getattr(cfg, "ROOM_MESSENGER_BRIDGE_SCRIPT", ""))
    if prefix:
        command_line = [*prefix, command]
    else:
        if not script.is_file():
            raise BridgeUnavailable("消息发送桥未就绪")
        command_line = [
            str(getattr(cfg, "ROOM_MESSENGER_BRIDGE_PYTHON", "python3")),
            str(script),
            command,
        ]
    try:
        proc = subprocess.run(
            command_line,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=BRIDGE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise BridgeUnavailable("消息发送桥响应超时")
    except OSError:
        raise BridgeUnavailable("消息发送桥暂时不可用")
    stdout = (proc.stdout or "").strip()
    parsed: dict[str, Any] = {}
    if stdout:
        try:
            candidate = json.loads(stdout.splitlines()[-1])
            if isinstance(candidate, dict):
                parsed = candidate
        except json.JSONDecodeError:
            parsed = {}
    if not parsed:
        raise BridgeUnavailable("消息发送桥返回异常")
    if not parsed.get("ok"):
        raise BridgeError(_safe_error(parsed.get("error"), "操作失败"))
    return parsed


# ── Auth ──────────────────────────────────────────────────────────────────


def _token(password: str) -> str:
    return password_session.cookie_token(password, context="room-messenger")


async def require_auth(
    request: Request,
    room_messenger_auth: str = Cookie(None, alias=AUTH_COOKIE),
    x_room_messenger_password: str = Header(None, alias="X-Room-Messenger-Password"),
):
    _require_enabled()
    expected = cfg.ROOM_MESSENGER_PASSWORD
    if room_messenger_auth and expected and hmac.compare_digest(room_messenger_auth, _token(expected)):
        return True
    if x_room_messenger_password and expected:
        if hmac.compare_digest(x_room_messenger_password, expected):
            return True
        check_admin_login_limit(
            get_client_ip(request), "消息发送页密码尝试过于频繁，请稍后再试", group="room_messenger"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要密码")


def _same_origin(request: Request) -> None:
    origin = str(request.headers.get("origin") or "").strip()
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host", ""):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请求来源无效")


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    _require_enabled()
    expected = cfg.ROOM_MESSENGER_PASSWORD
    if not expected or not hmac.compare_digest(payload.password, expected):
        check_admin_login_limit(
            get_client_ip(request), "消息发送页密码尝试过于频繁，请稍后再试", group="room_messenger"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    response.set_cookie(
        AUTH_COOKIE,
        _token(expected),
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
        path="/api/room-messenger",
    )
    _no_store(response)
    return {"success": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        key=AUTH_COOKIE,
        path="/api/room-messenger",
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
    )
    _no_store(response)
    return {"success": True}


@router.get("/verify")
async def verify(response: Response, _=Depends(require_auth)):
    _no_store(response)
    return {
        "verified": True,
        "node": cfg.SHARED_STATE_NODE_ID,
        "limits": _limits_payload(),
    }


def _limits_payload() -> dict[str, Any]:
    return {
        "min_interval": max(5, int(getattr(cfg, "ROOM_MESSENGER_MIN_INTERVAL_SECONDS", 15))),
        "default_interval": max(
            int(getattr(cfg, "ROOM_MESSENGER_MIN_INTERVAL_SECONDS", 15)),
            int(getattr(cfg, "ROOM_MESSENGER_DEFAULT_INTERVAL_SECONDS", 60)),
        ),
        "max_jitter": max(0, int(getattr(cfg, "ROOM_MESSENGER_MAX_JITTER_SECONDS", 120))),
        "max_batch": max(1, int(getattr(cfg, "ROOM_MESSENGER_MAX_BATCH_MESSAGES", 30))),
        "daily_cap": max(1, int(getattr(cfg, "ROOM_MESSENGER_DAILY_SEND_CAP", 100))),
        "history_poll": max(5, int(getattr(cfg, "ROOM_MESSENGER_HISTORY_POLL_SECONDS", 20))),
        "max_text_length": MAX_TEXT_LENGTH,
        "timezone": "Asia/Shanghai",
        "confirm_word": SEND_CONFIRM_WORD,
    }


# ── Account binding ───────────────────────────────────────────────────────


def _binding_path() -> Path:
    return _state_path("binding.json")


def _binding() -> dict[str, Any]:
    payload = _read_json(_binding_path(), {})
    account_id = str(payload.get("account_id") or "")
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        return {}
    return payload


def _set_binding(account_id: str, nickname: str) -> dict[str, Any]:
    payload = {
        "account_id": account_id,
        "nickname": nickname,
        "bound_at": _now_iso(),
    }
    _write_json(_binding_path(), payload)
    return payload


def _clear_binding() -> None:
    try:
        _binding_path().unlink(missing_ok=True)
    except OSError:
        pass


def _resolve_account_id(account_id: str | None) -> str:
    candidate = str(account_id or "").strip()
    if candidate:
        if not ACCOUNT_ID_RE.fullmatch(candidate):
            raise HTTPException(status_code=422, detail="账号 ID 无效")
        return candidate
    binding = _binding()
    if not binding:
        raise HTTPException(status_code=409, detail="请先登录并绑定个人账号")
    return str(binding["account_id"])


@router.get("/account")
def account_status(response: Response, _=Depends(require_auth)):
    _no_store(response)
    try:
        data = _run_bridge("messenger-status", {})
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    binding = _binding()
    if binding and not any(str(item.get("id")) == str(binding.get("account_id")) for item in accounts):
        binding = {}
    return {
        "accounts": accounts,
        "binding": binding,
        "limits": _limits_payload(),
        "daily_sent": _daily_sent(binding.get("account_id")) if binding else 0,
    }


@router.post("/account/bind")
def bind_account(payload: dict, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    account_id = str(payload.get("account_id") or "").strip()
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise HTTPException(status_code=422, detail="账号 ID 无效")
    try:
        data = _run_bridge("messenger-status", {})
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    match = next((item for item in accounts if str(item.get("id")) == account_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="个人账号不存在")
    if not match.get("has_token"):
        raise HTTPException(status_code=400, detail="该账号 Token 缺失，请重新登录")
    binding = _set_binding(account_id, str(match.get("nickname") or ""))
    return {"binding": binding}


@router.post("/account/unbind")
async def unbind_account(request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    _clear_binding()
    return {"success": True}


class SmsRequest(BaseModel):
    phone: str
    area: str = "86"


class SecurityRequest(BaseModel):
    session_id: str
    option: str


class CodeRequest(BaseModel):
    session_id: str
    code: str


@router.post("/account/send-sms")
def account_send_sms(payload: SmsRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    try:
        return _run_bridge("send-sms", {"phone": payload.phone, "area": payload.area})
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BridgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/account/security-answer")
def account_security_answer(payload: SecurityRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    try:
        return _run_bridge(
            "security-answer", {"session_id": payload.session_id, "option": payload.option}
        )
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BridgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/account/verify-code")
def account_verify_code(payload: CodeRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    try:
        data = _run_bridge(
            "verify-code",
            {"session_id": payload.session_id, "code": payload.code, "personal_only": True},
        )
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BridgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    account_id = str(account.get("id") or "")
    nickname = str(account.get("nickname") or "")
    if account_id:
        _set_binding(account_id, nickname)
    return {"account": account, "binding": _binding() if account_id else {}}


class ProbeRequest(BaseModel):
    account_id: str = ""


@router.post("/account/probe")
def account_probe(payload: ProbeRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    account_id = _resolve_account_id(payload.account_id)
    try:
        return _run_bridge("messenger-probe", {"account_id": account_id})
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BridgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Member catalog ────────────────────────────────────────────────────────


def _catalog_path() -> Path:
    return Path(
        getattr(
            cfg,
            "ROOM_MESSENGER_CATALOG_PATH",
            "/home/snh48-fan-hub/room_record/陈嘉仪_161808449/cross_room/metadata/member_catalog.json",
        )
    )


def _room_config_path() -> Path:
    return Path(
        getattr(
            cfg,
            "ROOM_MESSENGER_ROOM_CONFIG_PATH",
            "/home/snh48-fan-hub/config/room_monitor.json",
        )
    )


def _load_catalog() -> list[dict[str, Any]]:
    global _catalog_cache
    path = _catalog_path()
    room_config_path = _room_config_path()
    try:
        catalog_mtime = path.stat().st_mtime
    except OSError:
        catalog_mtime = -1.0
    try:
        config_mtime = room_config_path.stat().st_mtime
    except OSError:
        config_mtime = -1.0
    if catalog_mtime < 0 and config_mtime < 0:
        return []
    signature = (catalog_mtime, config_mtime)
    with _catalog_lock:
        if _catalog_cache and _catalog_cache[0] == signature:
            return _catalog_cache[1]
        members: dict[str, dict[str, Any]] = {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        rooms = raw.get("rooms") if isinstance(raw.get("rooms"), list) else []
        for room in rooms:
            if not isinstance(room, dict):
                continue
            owner_id = str(room.get("owner_id") or "").strip()
            channel_id = str(room.get("channel_id") or "").strip()
            if not owner_id.isdigit() or not channel_id.isdigit():
                continue
            owner_name = str(room.get("owner_name") or owner_id).strip()
            group_name = str(room.get("group_name") or "").strip()
            entry = members.setdefault(
                owner_id,
                {
                    "id": owner_id,
                    "name": owner_name,
                    "group": group_name,
                    "in_group": bool(room.get("in_group")),
                    "rooms": [],
                },
            )
            if not entry.get("in_group"):
                entry["in_group"] = bool(room.get("in_group"))
            entry["rooms"].append(
                {
                    "channel_id": channel_id,
                    "server_id": str(room.get("server_id") or ""),
                    "room_type": "small" if str(room.get("room_type")) == "small" else "main",
                    "room_label": str(
                        room.get("room_label")
                        or ("小房间" if str(room.get("room_type")) == "small" else "公开房间")
                    ),
                }
            )
        # The cross-room catalog is built from a public member index that does
        # not always contain monitored members (for example the owner's own
        # rooms). Merge the locally monitored member configuration so those
        # rooms are always selectable.
        try:
            room_config = json.loads(room_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            room_config = {}
        configured = room_config.get("members") if isinstance(room_config.get("members"), list) else []
        configured_ids = {
            str(member.get("id") or "").strip()
            for member in configured
            if isinstance(member, dict) and str(member.get("id") or "").strip().isdigit()
        }
        for member in configured:
            if not isinstance(member, dict):
                continue
            owner_id = str(member.get("id") or "").strip()
            owner_name = str(member.get("name") or "").strip()
            if not owner_id.isdigit() or not owner_name:
                continue
            entry = members.setdefault(
                owner_id,
                {
                    "id": owner_id,
                    "name": owner_name,
                    "group": "",
                    "in_group": True,
                    "rooms": [],
                },
            )
            known_channels = {str(item.get("channel_id")) for item in entry["rooms"]}
            main_channel = str(member.get("channelId") or "").strip()
            main_server = str(member.get("serverId") or "").strip()
            if main_channel.isdigit() and main_channel not in known_channels:
                entry["rooms"].append(
                    {
                        "channel_id": main_channel,
                        "server_id": main_server,
                        "room_type": "main",
                        "room_label": "公开房间",
                    }
                )
                known_channels.add(main_channel)
            for extra in member.get("rooms", []) or []:
                if not isinstance(extra, dict):
                    continue
                channel_id = str(extra.get("channelId") or "").strip()
                if not channel_id.isdigit() or channel_id in known_channels:
                    continue
                room_type = "small" if str(extra.get("type")) == "small" else "main"
                entry["rooms"].append(
                    {
                        "channel_id": channel_id,
                        "server_id": str(extra.get("serverId") or main_server),
                        "room_type": room_type,
                        "room_label": str(extra.get("label") or ("小房间" if room_type == "small" else "公开房间")),
                    }
                )
                known_channels.add(channel_id)
        rows = list(members.values())
        for row in rows:
            row["rooms"].sort(key=lambda item: (0 if item["room_type"] == "main" else 1, item["channel_id"]))
            row["room_count"] = len(row["rooms"])
            row["search"] = f"{row['name']} {row['id']} {row['group']}".lower()
        rows.sort(
            key=lambda row: (
                0 if row["id"] in configured_ids else 1,
                0 if row.get("in_group") else 1,
                _GROUP_ORDER.get(str(row.get("group") or ""), 99),
                str(row.get("name") or ""),
            )
        )
        _catalog_cache = (signature, rows)
        return rows


@router.get("/catalog")
async def catalog(
    response: Response,
    q: str = Query("", max_length=60),
    group: str = Query("", max_length=20),
    limit: int = Query(40, ge=1, le=MAX_CATALOG_PAGE),
    offset: int = Query(0, ge=0),
    _=Depends(require_auth),
):
    _no_store(response)
    rows = _load_catalog()
    query = q.strip().lower()
    group_filter = group.strip()
    if query:
        rows = [row for row in rows if query in row["search"]]
    if group_filter:
        rows = [row for row in rows if row.get("group") == group_filter]
    total = len(rows)
    page = rows[offset : offset + limit]
    public = [
        {
            "id": row["id"],
            "name": row["name"],
            "group": row["group"],
            "in_group": row["in_group"],
            "rooms": row["rooms"],
        }
        for row in page
    ]
    groups = sorted(
        {row.get("group") for row in _load_catalog() if row.get("group")},
        key=lambda value: (_GROUP_ORDER.get(value, 99), value),
    )
    return {"total": total, "offset": offset, "limit": limit, "members": public, "groups": groups}


# ── Recent channels ───────────────────────────────────────────────────────


def _recent_path() -> Path:
    return _state_path("recent.json")


def _recent_rows(account_id: str) -> list[dict[str, Any]]:
    payload = _read_json(_recent_path(), {})
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    rows = accounts.get(account_id) if isinstance(accounts.get(account_id), list) else []
    return [item for item in rows if isinstance(item, dict)][:MAX_RECENT_CHANNELS]


def _record_recent(account_id: str, channel: dict[str, Any]) -> None:
    channel_id = str(channel.get("channel_id") or "")
    if not CHANNEL_ID_RE.fullmatch(channel_id):
        return
    with _state_lock:
        payload = _read_json(_recent_path(), {})
        accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
        rows = [item for item in accounts.get(account_id, []) if isinstance(item, dict)]
        rows = [item for item in rows if str(item.get("channel_id")) != channel_id]
        rows.insert(
            0,
            {
                "channel_id": channel_id,
                "server_id": str(channel.get("server_id") or ""),
                "member_id": str(channel.get("member_id") or ""),
                "member_name": str(channel.get("member_name") or ""),
                "group": str(channel.get("group") or ""),
                "room_type": "small" if channel.get("room_type") == "small" else "main",
                "room_label": str(channel.get("room_label") or ""),
                "last_used_at": _now_iso(),
            },
        )
        accounts[account_id] = rows[:MAX_RECENT_CHANNELS]
        _write_json(_recent_path(), {"accounts": accounts, "updated_at": _now_iso()})


@router.get("/recent")
async def recent_channels(response: Response, account_id: str = "", _=Depends(require_auth)):
    _no_store(response)
    resolved = _resolve_account_id(account_id)
    return {"account_id": resolved, "channels": _recent_rows(resolved)}


class RecentRequest(BaseModel):
    account_id: str = ""
    channel_id: str
    server_id: str = ""
    member_id: str = ""
    member_name: str = ""
    group: str = ""
    room_type: str = "main"
    room_label: str = ""


@router.post("/recent")
async def record_recent(payload: RecentRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    account_id = _resolve_account_id(payload.account_id)
    if not CHANNEL_ID_RE.fullmatch(payload.channel_id):
        raise HTTPException(status_code=422, detail="频道 ID 无效")
    _record_recent(
        account_id,
        {
            "channel_id": payload.channel_id,
            "server_id": payload.server_id,
            "member_id": payload.member_id,
            "member_name": payload.member_name,
            "group": payload.group,
            "room_type": payload.room_type,
            "room_label": payload.room_label,
        },
    )
    return {"channels": _recent_rows(account_id)}


@router.delete("/recent")
async def delete_recent(
    request: Request,
    response: Response,
    channel_id: str = Query(..., min_length=1, max_length=32),
    account_id: str = "",
    _=Depends(require_auth),
):
    _same_origin(request)
    _no_store(response)
    resolved = _resolve_account_id(account_id)
    with _state_lock:
        payload = _read_json(_recent_path(), {})
        accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
        rows = [item for item in accounts.get(resolved, []) if isinstance(item, dict)]
        accounts[resolved] = [item for item in rows if str(item.get("channel_id")) != channel_id]
        _write_json(_recent_path(), {"accounts": accounts, "updated_at": _now_iso()})
    return {"channels": _recent_rows(resolved)}


# ── History ───────────────────────────────────────────────────────────────


@router.get("/messages")
def messages(
    response: Response,
    channel_id: str = Query(..., min_length=1, max_length=32),
    server_id: str = Query("", max_length=32),
    next_time: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=50),
    account_id: str = "",
    _=Depends(require_auth),
):
    _no_store(response)
    if not CHANNEL_ID_RE.fullmatch(channel_id):
        raise HTTPException(status_code=422, detail="频道 ID 无效")
    resolved = _resolve_account_id(account_id)
    try:
        data = _run_bridge(
            "messenger-history",
            {
                "account_id": resolved,
                "channel_id": channel_id,
                "server_id": server_id,
                "next_time": next_time,
                "limit": limit,
            },
        )
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BridgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return data


# ── Manual send ───────────────────────────────────────────────────────────


class SendItem(BaseModel):
    channel_id: str
    server_id: str
    text: str


class SendRequest(BaseModel):
    account_id: str = ""
    channel_id: str
    server_id: str
    text: str
    confirm: str
    channel: dict[str, Any] = Field(default_factory=dict)


def _daily_path() -> Path:
    return _state_path("daily.json")


def _daily_sent(account_id: str) -> int:
    payload = _read_json(_daily_path(), {})
    if str(payload.get("date") or "") != _today():
        return 0
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    try:
        return int(counts.get(account_id) or 0)
    except (TypeError, ValueError):
        return 0


def _add_daily_sent(account_id: str, amount: int) -> int:
    with _state_lock:
        payload = _read_json(_daily_path(), {})
        if str(payload.get("date") or "") != _today():
            payload = {"date": _today(), "counts": {}}
        counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
        current = int(counts.get(account_id) or 0) + max(0, amount)
        counts[account_id] = current
        _write_json(_daily_path(), {"date": _today(), "counts": counts, "updated_at": _now_iso()})
        return current


def _append_audit(entry: dict[str, Any]) -> None:
    path = _state_path("audit.jsonl")
    try:
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except OSError:
        logger.warning("room messenger audit write failed", exc_info=False)


@router.post("/send")
def send_now(payload: SendRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    if payload.confirm != SEND_CONFIRM_WORD:
        raise HTTPException(status_code=422, detail=f"请输入确认词“{SEND_CONFIRM_WORD}”")
    account_id = _resolve_account_id(payload.account_id)
    if not CHANNEL_ID_RE.fullmatch(payload.channel_id):
        raise HTTPException(status_code=422, detail="频道 ID 无效")
    text = payload.text.strip()
    if not text or len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=422, detail=f"消息长度必须在 1-{MAX_TEXT_LENGTH} 字之间")
    cap = _limits_payload()["daily_cap"]
    if _daily_sent(account_id) >= cap:
        raise HTTPException(status_code=429, detail=f"已达到今日发送上限（{cap} 条）")
    msg_id = os.urandom(16).hex()
    try:
        data = _run_bridge(
            "messenger-send",
            {
                "account_id": account_id,
                "gap_seconds": 1,
                "jitter_seconds": 0,
                "timeout_seconds": 120,
                "items": [
                    {
                        "channel_id": payload.channel_id,
                        "server_id": payload.server_id,
                        "text": text,
                        "msg_id_client": msg_id,
                    }
                ],
            },
        )
    except BridgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BridgeError as exc:
        _append_audit(
            {
                "at": _now_iso(),
                "kind": "manual",
                "account_id": account_id,
                "channel_id": payload.channel_id,
                "ok": False,
                "error": str(exc),
                "text_length": len(text),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "preview": _message_preview(text, 40),
            }
        )
        raise HTTPException(status_code=400, detail=str(exc))
    result = (data.get("results") or [{}])[0]
    ok = bool(result.get("ok"))
    error = _safe_error(result.get("error"), "") if not ok else ""
    if ok:
        _add_daily_sent(account_id, 1)
    _append_audit(
        {
            "at": _now_iso(),
            "kind": "manual",
            "account_id": account_id,
            "channel_id": payload.channel_id,
            "ok": ok,
            "error": error,
            "msg_id_client": msg_id,
            "text_length": len(text),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            "preview": _message_preview(text, 40),
        }
    )
    if ok and payload.channel:
        _record_recent(
            account_id,
            {
                **payload.channel,
                "channel_id": payload.channel_id,
                "server_id": payload.server_id,
            },
        )
    return {
        "ok": ok,
        "error": error,
        "msg_id_client": msg_id,
        "daily_sent": _daily_sent(account_id),
        "daily_cap": cap,
    }


# ── Jobs ──────────────────────────────────────────────────────────────────


def _jobs_path() -> Path:
    return _state_path("jobs.json")


def _load_jobs() -> dict[str, dict[str, Any]]:
    payload = _read_json(_jobs_path(), {})
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    return {str(key): value for key, value in jobs.items() if isinstance(value, dict)}


def _save_jobs(jobs: dict[str, dict[str, Any]]) -> None:
    ordered = sorted(jobs.items(), key=lambda item: str(item[1].get("created_at") or ""), reverse=True)
    trimmed = dict(ordered[:MAX_JOB_HISTORY])
    _write_json(_jobs_path(), {"jobs": trimmed, "updated_at": _now_iso()})


def _parse_start_at(value: str | None, default_offset: int = 5) -> float:
    text = str(value or "").strip()
    if not text:
        return time.time() + default_offset
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise HTTPException(status_code=422, detail="开始时间格式无效")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    timestamp = parsed.timestamp()
    if timestamp < time.time() - 120:
        raise HTTPException(status_code=422, detail="开始时间不能早于当前时间")
    return timestamp


def _next_daily_timestamp(base: float) -> float:
    """Return the next occurrence of the same local wall-clock time."""
    moment = datetime.fromtimestamp(base, TZ)
    tomorrow = moment + timedelta(days=1)
    return tomorrow.timestamp()


def _job_public(job: dict[str, Any]) -> dict[str, Any]:
    messages = job.get("messages") if isinstance(job.get("messages"), list) else []
    sent = sum(1 for item in messages if isinstance(item, dict) and item.get("status") == "sent")
    failed = sum(1 for item in messages if isinstance(item, dict) and item.get("status") in {"failed", "unknown"})
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "mode": job.get("mode"),
        "repeat_daily": bool(job.get("repeat_daily")),
        "account_id": job.get("account_id"),
        "channel": job.get("channel") if isinstance(job.get("channel"), dict) else {},
        "interval_seconds": job.get("interval_seconds"),
        "jitter_seconds": job.get("jitter_seconds"),
        "next_run_at": job.get("next_run_at"),
        "next_run_label": (
            datetime.fromtimestamp(float(job.get("next_run_at")), TZ).strftime("%Y-%m-%d %H:%M:%S")
            if job.get("next_run_at")
            else ""
        ),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "last_error": _safe_error(job.get("last_error"), "") if job.get("last_error") else "",
        "total": len(messages),
        "sent": sent,
        "failed": failed,
        "pending": sum(1 for item in messages if isinstance(item, dict) and item.get("status") == "pending"),
        "messages": [
            {
                "index": index,
                "text": str(item.get("text") or ""),
                "status": item.get("status"),
                "sent_at": item.get("sent_at") or "",
                "error": _safe_error(item.get("error"), "") if item.get("error") else "",
            }
            for index, item in enumerate(messages)
            if isinstance(item, dict)
        ],
    }


class JobRequest(BaseModel):
    account_id: str = ""
    channel: dict[str, Any]
    messages: list[str]
    interval_seconds: int = 60
    jitter_seconds: int = 0
    start_at: str = ""
    repeat_daily: bool = False
    confirm: bool = False


@router.get("/jobs")
async def list_jobs(response: Response, account_id: str = "", _=Depends(require_auth)):
    _no_store(response)
    jobs = _load_jobs()
    rows = list(jobs.values())
    if account_id:
        rows = [row for row in rows if str(row.get("account_id")) == account_id]
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    binding = _binding()
    binding_id = str(binding.get("account_id") or "")
    return {
        "jobs": [_job_public(row) for row in rows],
        "limits": _limits_payload(),
        "daily_sent": _daily_sent(binding_id) if binding_id else 0,
    }


@router.post("/jobs")
async def create_job(payload: JobRequest, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    if not payload.confirm:
        raise HTTPException(status_code=422, detail="请确认定时/批量发送计划")
    account_id = _resolve_account_id(payload.account_id)
    limits = _limits_payload()
    channel = payload.channel if isinstance(payload.channel, dict) else {}
    channel_id = str(channel.get("channel_id") or "")
    server_id = str(channel.get("server_id") or "")
    if not CHANNEL_ID_RE.fullmatch(channel_id):
        raise HTTPException(status_code=422, detail="频道 ID 无效")
    if not CHANNEL_ID_RE.fullmatch(server_id):
        raise HTTPException(status_code=422, detail="服务器 ID 无效")
    messages = [str(item).strip() for item in payload.messages if str(item or "").strip()]
    if not messages:
        raise HTTPException(status_code=422, detail="请填写至少一条消息")
    if len(messages) > limits["max_batch"]:
        raise HTTPException(status_code=422, detail=f"单次最多 {limits['max_batch']} 条消息")
    if any(len(item) > MAX_TEXT_LENGTH for item in messages):
        raise HTTPException(status_code=422, detail=f"单条消息不能超过 {MAX_TEXT_LENGTH} 字")
    interval = max(limits["min_interval"], int(payload.interval_seconds or limits["default_interval"]))
    jitter = max(0, min(limits["max_jitter"], int(payload.jitter_seconds or 0)))
    start_at = _parse_start_at(payload.start_at)
    repeat_daily = bool(payload.repeat_daily)
    if repeat_daily:
        mode = "daily"
    elif len(messages) > 1:
        mode = "batch"
    else:
        mode = "once"
    job_id = os.urandom(16).hex()
    now = _now_iso()
    job = {
        "id": job_id,
        "account_id": account_id,
        "channel": {
            "channel_id": channel_id,
            "server_id": server_id,
            "member_id": str(channel.get("member_id") or ""),
            "member_name": str(channel.get("member_name") or ""),
            "group": str(channel.get("group") or ""),
            "room_type": "small" if channel.get("room_type") == "small" else "main",
            "room_label": str(channel.get("room_label") or ""),
        },
        "mode": mode,
        "repeat_daily": repeat_daily,
        "messages": [
            {"text": text, "status": "pending", "sent_at": "", "error": ""} for text in messages
        ],
        "interval_seconds": interval,
        "jitter_seconds": jitter,
        "next_run_at": start_at,
        "daily_time": datetime.fromtimestamp(start_at, TZ).strftime("%H:%M:%S") if repeat_daily else "",
        "created_at": now,
        "updated_at": now,
        "status": "scheduled",
        "last_error": "",
        "last_sent_at": 0,
    }
    with _state_lock:
        jobs = _load_jobs()
        jobs[job_id] = job
        _save_jobs(jobs)
    _append_audit(
        {
            "at": now,
            "kind": "job_created",
            "job_id": job_id,
            "account_id": account_id,
            "channel_id": channel_id,
            "mode": mode,
            "total": len(messages),
            "interval": interval,
            "jitter": jitter,
            "repeat_daily": repeat_daily,
            "next_run_at": start_at,
        }
    )
    return {"job": _job_public(job)}


def _job_action(job_id: str, action: str) -> dict[str, Any]:
    if not JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    with _state_lock:
        jobs = _load_jobs()
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        now = _now_iso()
        if action == "pause":
            if job.get("status") not in {"scheduled", "running"}:
                raise HTTPException(status_code=409, detail="当前任务不能暂停")
            job["status"] = "paused"
        elif action == "resume":
            if job.get("status") not in {"paused", "failed"}:
                raise HTTPException(status_code=409, detail="当前任务不能继续")
            # Definitive failures can be retried; ``unknown`` means the send
            # result was not acknowledged and must not be resent automatically.
            for item in job.get("messages", []):
                if isinstance(item, dict) and item.get("status") == "failed":
                    item["status"] = "pending"
                    item["error"] = ""
            job["status"] = "scheduled"
            job["next_run_at"] = time.time() + 3
            job["last_error"] = ""
        elif action == "cancel":
            if job.get("status") in {"completed", "cancelled"}:
                raise HTTPException(status_code=409, detail="任务已结束")
            job["status"] = "cancelled"
            for item in job.get("messages", []):
                if isinstance(item, dict) and item.get("status") in {"pending", "sending"}:
                    item["status"] = "cancelled"
        else:
            raise HTTPException(status_code=404, detail="未知操作")
        job["updated_at"] = now
        jobs[job_id] = job
        _save_jobs(jobs)
    return _job_public(job)


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    return {"job": _job_action(job_id, "pause")}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    return {"job": _job_action(job_id, "resume")}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request, response: Response, _=Depends(require_auth)):
    _same_origin(request)
    _no_store(response)
    return {"job": _job_action(job_id, "cancel")}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, response: Response, _=Depends(require_auth)):
    _no_store(response)
    jobs = _load_jobs()
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"job": _job_public(job)}


# ── Scheduler ─────────────────────────────────────────────────────────────


def _recover_jobs() -> None:
    """Convert interrupted ``sending`` items to ``unknown`` exactly once."""
    global _scheduler_recovered
    with _state_lock:
        if _scheduler_recovered:
            return
        jobs = _load_jobs()
        changed = False
        for job in jobs.values():
            if job.get("status") == "running":
                job["status"] = "paused"
                job["last_error"] = "网站重启中断发送，请核对记录后手动继续"
                job["updated_at"] = _now_iso()
                changed = True
            for item in job.get("messages", []):
                if isinstance(item, dict) and item.get("status") == "sending":
                    item["status"] = "unknown"
                    item["error"] = "发送结果未知，未自动重发"
                    changed = True
        if changed:
            _save_jobs(jobs)
        _scheduler_recovered = True


def _chunk_size(job: dict[str, Any], pending_count: int, account_id: str) -> int:
    limits = _limits_payload()
    interval = max(1, int(job.get("interval_seconds") or limits["default_interval"]))
    chunk_seconds = max(30, int(getattr(cfg, "ROOM_MESSENGER_CHUNK_SECONDS", 300)))
    by_time = max(1, chunk_seconds // interval)
    remaining = max(0, limits["daily_cap"] - _daily_sent(account_id))
    if remaining <= 0:
        return 0
    return min(10, limits["max_batch"], pending_count, by_time, remaining)


def _run_job(job_id: str) -> None:
    while True:
        with _state_lock:
            jobs = _load_jobs()
            job = jobs.get(job_id)
            if not job or job.get("status") != "running":
                return
            messages = job.get("messages") if isinstance(job.get("messages"), list) else []
            pending = [
                (index, item)
                for index, item in enumerate(messages)
                if isinstance(item, dict) and item.get("status") == "pending"
            ]
            if not pending:
                break
            account_id = str(job.get("account_id") or "")
            chunk_size = _chunk_size(job, len(pending), account_id)
            if chunk_size <= 0:
                job["status"] = "paused"
                job["last_error"] = "已达到今日发送上限，任务已暂停"
                job["updated_at"] = _now_iso()
                jobs[job_id] = job
                _save_jobs(jobs)
                return
            chunk = pending[:chunk_size]
            for _index, item in chunk:
                item["status"] = "sending"
            job["updated_at"] = _now_iso()
            jobs[job_id] = job
            _save_jobs(jobs)
            channel = job.get("channel") if isinstance(job.get("channel"), dict) else {}
            interval = int(job.get("interval_seconds") or 60)
            jitter = int(job.get("jitter_seconds") or 0)
            last_sent_at = float(job.get("last_sent_at") or 0)
            chunk_payload = [
                {
                    "channel_id": str(channel.get("channel_id") or ""),
                    "server_id": str(channel.get("server_id") or ""),
                    "text": str(item.get("text") or ""),
                    "msg_id_client": os.urandom(16).hex(),
                }
                for _index, item in chunk
            ]
            for (_index, item), payload in zip(chunk, chunk_payload):
                item["msg_id_client"] = payload["msg_id_client"]

        # Respect the interval across chunk boundaries (the bridge handles
        # spacing inside a chunk).
        if last_sent_at:
            expected = last_sent_at + interval
            wait_seconds = expected - time.time()
            if wait_seconds > 0:
                time.sleep(min(wait_seconds, interval + 5))
        try:
            data = _run_bridge(
                "messenger-send",
                {
                    "account_id": account_id,
                    "gap_seconds": interval,
                    "jitter_seconds": jitter,
                    "timeout_seconds": min(300, max(30, len(chunk) * interval + 30)),
                    "items": chunk_payload,
                },
            )
            results = data.get("results") if isinstance(data.get("results"), list) else []
        except BridgeUnavailable as exc:
            with _state_lock:
                jobs = _load_jobs()
                job = jobs.get(job_id) or {}
                current = job.get("messages") if isinstance(job.get("messages"), list) else []
                for index, _item in chunk:
                    if 0 <= index < len(current) and isinstance(current[index], dict):
                        current[index]["status"] = "unknown"
                        current[index]["error"] = "发送桥超时或不可用，结果未知"
                job["status"] = "paused"
                job["last_error"] = str(exc)
                job["updated_at"] = _now_iso()
                jobs[job_id] = job
                _save_jobs(jobs)
            return
        except BridgeError as exc:
            with _state_lock:
                jobs = _load_jobs()
                job = jobs.get(job_id) or {}
                current = job.get("messages") if isinstance(job.get("messages"), list) else []
                for index, _item in chunk:
                    if 0 <= index < len(current) and isinstance(current[index], dict):
                        current[index]["status"] = "failed"
                        current[index]["error"] = str(exc)
                job["status"] = "failed"
                job["last_error"] = str(exc)
                job["updated_at"] = _now_iso()
                jobs[job_id] = job
                _save_jobs(jobs)
            return

        with _state_lock:
            jobs = _load_jobs()
            job = jobs.get(job_id) or {}
            sent_count = 0
            current = job.get("messages") if isinstance(job.get("messages"), list) else []
            for offset, (index, _item) in enumerate(chunk):
                result = results[offset] if 0 <= offset < len(results) else {}
                if not (0 <= index < len(current)) or not isinstance(current[index], dict):
                    continue
                target = current[index]
                if bool(result.get("ok")):
                    target["status"] = "sent"
                    target["sent_at"] = _now_iso()
                    target["error"] = ""
                    sent_count += 1
                else:
                    target["status"] = "failed"
                    target["error"] = _safe_error(result.get("error"), "发送失败")
            job["last_sent_at"] = time.time() if sent_count else float(job.get("last_sent_at") or 0)
            job["updated_at"] = _now_iso()
            job["status"] = job.get("status") or "running"
            jobs[job_id] = job
            _save_jobs(jobs)
            if sent_count:
                _add_daily_sent(account_id, sent_count)
                _append_audit(
                    {
                        "at": _now_iso(),
                        "kind": "job_chunk",
                        "job_id": job_id,
                        "account_id": account_id,
                        "channel_id": str(channel.get("channel_id") or ""),
                        "sent": sent_count,
                        "failed": len(chunk) - sent_count,
                    }
                )
            if sent_count == 0:
                job["status"] = "paused"
                job["last_error"] = "本批发送全部失败，任务已暂停"
                jobs[job_id] = job
                _save_jobs(jobs)
                return

    for _attempt in range(4):
        with _state_lock:
            jobs = _load_jobs()
            job = jobs.get(job_id)
            if not job or job.get("status") != "running":
                return
            messages = job.get("messages") if isinstance(job.get("messages"), list) else []
            if any(isinstance(item, dict) and item.get("status") in {"pending", "sending"} for item in messages):
                return
            if job.get("repeat_daily"):
                for item in messages:
                    if isinstance(item, dict):
                        item["status"] = "pending"
                        item["sent_at"] = ""
                        item["error"] = ""
                base = float(job.get("next_run_at") or time.time())
                next_run = _next_daily_timestamp(base)
                while next_run <= time.time():
                    next_run = _next_daily_timestamp(next_run)
                job["next_run_at"] = next_run
                job["status"] = "scheduled"
                job["updated_at"] = _now_iso()
            else:
                job["status"] = "completed"
                job["updated_at"] = _now_iso()
            jobs[job_id] = job
            _save_jobs(jobs)
            return


def _scheduler_tick() -> None:
    _recover_jobs()
    now = time.time()
    with _state_lock:
        jobs = _load_jobs()
        candidates = [
            job
            for job in jobs.values()
            if job.get("status") == "scheduled" and float(job.get("next_run_at") or 0) <= now
        ]
        if not candidates:
            return
        job = min(candidates, key=lambda item: float(item.get("next_run_at") or 0))
        job_id = str(job.get("id") or "")
        if job.get("repeat_daily") and now - float(job.get("next_run_at") or 0) > 3600:
            base = float(job.get("next_run_at") or now)
            next_run = _next_daily_timestamp(base)
            while next_run <= now:
                next_run = _next_daily_timestamp(next_run)
            job["next_run_at"] = next_run
            job["last_error"] = "错过计划时间，已顺延到下一次"
            job["updated_at"] = _now_iso()
            jobs[job_id] = job
            _save_jobs(jobs)
            return
        job["status"] = "running"
        job["updated_at"] = _now_iso()
        jobs[job_id] = job
        _save_jobs(jobs)
    try:
        _run_job(job_id)
    except Exception:
        logger.exception("room messenger job failed: %s", job_id)
        with _state_lock:
            jobs = _load_jobs()
            job = jobs.get(job_id) or {}
            job["status"] = "paused"
            job["last_error"] = "任务执行异常，已暂停"
            job["updated_at"] = _now_iso()
            jobs[job_id] = job
            _save_jobs(jobs)


def _scheduler_loop() -> None:
    while True:
        try:
            _scheduler_tick()
        except Exception:
            logger.exception("room messenger scheduler tick failed")
        time.sleep(2)


def start_scheduler() -> bool:
    global _scheduler_started
    if not cfg.ROOM_MESSENGER_ENABLED:
        return False
    with _state_lock:
        if _scheduler_started:
            return True
        _scheduler_started = True
    _state_dir()
    thread = threading.Thread(target=_scheduler_loop, name="room-messenger-scheduler", daemon=True)
    thread.start()
    return True

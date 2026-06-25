"""
Room messages API router.

Exposes a password-protected, cursor-based view over the room_monitor
messages.csv dataset. The CSV is cached in memory and reloaded when the file
mtime changes.
"""
from __future__ import annotations

import csv
import hmac
import json
import os
import posixpath
import re
import shlex
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from website import config as cfg
from website.rate_limiter import check_admin_login_limit, get_client_ip

router = APIRouter(prefix="/api/room-messages", tags=["房间消息页"])

VALID_FAMILIES = {"all", "text", "reply", "gift", "gift_reply", "media", "flipcard", "live", "share", "event"}
VALID_MEDIA_FILTERS = {"all", "with", "without"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TYPE_LABELS = {
    "TEXT": "文本",
    "REPLY": "文字回复",
    "GIFT_TEXT": "礼物",
    "GIFTREPLY": "回礼物",
    "AUDIO_GIFT_REPLY": "语音回礼物",
    "IMAGE": "图片",
    "VIDEO": "视频",
    "AUDIO": "语音",
    "AUDIO_REPLY": "语音回复",
    "EXPRESSIMAGE": "表情包",
    "LIVEPUSH": "直播推送",
    "FLIPCARD": "文字翻牌",
    "FLIPCARD_AUDIO": "语音翻牌",
    "FLIPCARD_VIDEO": "视频翻牌",
    "SHARE_POSTS": "动态分享",
    "RED_PACKET_2026": "红包",
}

TYPE_FAMILIES = {
    "TEXT": "text",
    "REPLY": "reply",
    "AUDIO_REPLY": "reply",
    "GIFT_TEXT": "gift",
    "GIFTREPLY": "gift_reply",
    "AUDIO_GIFT_REPLY": "gift_reply",
    "IMAGE": "media",
    "VIDEO": "media",
    "AUDIO": "media",
    "EXPRESSIMAGE": "media",
    "FLIPCARD": "flipcard",
    "FLIPCARD_AUDIO": "flipcard",
    "FLIPCARD_VIDEO": "flipcard",
    "LIVEPUSH": "live",
    "SHARE_POSTS": "share",
    "RED_PACKET_2026": "event",
}

_cache_lock = threading.Lock()
_cache_mtime_ns = -1
_cache_ignore_mtime_ns = -2
_cache_rows: list[dict[str, Any]] = []
_cache_summary: dict[str, Any] = {}
_ignore_lock = threading.Lock()


class _IgnoreGitSyncError(Exception):
    """Raised when the ignored-state Git sync fails."""


class _IgnoreGitRaceError(_IgnoreGitSyncError):
    """Raised when another server pushed the state first."""


class _IgnoreDirectSyncError(Exception):
    """Raised when direct ignored-state sync to the peer server fails."""


async def verify_room_messages_password(
    request: Request,
    x_room_messages_password: str = Header(None, alias="X-Room-Messages-Password"),
):
    """Verify room messages page password."""
    expected = cfg.ROOM_MESSAGES_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="房间消息页未启用",
        )
    if not x_room_messages_password:
        check_room_messages_login_limit(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要密码",
        )
    if not hmac.compare_digest(expected, x_room_messages_password):
        check_room_messages_login_limit(request)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="密码错误",
        )
    return True


def check_room_messages_login_limit(request: Request) -> None:
    check_admin_login_limit(get_client_ip(request), "房间消息页密码尝试过于频繁，请稍后再试")


@router.get("/data")
def get_room_messages_data(
    response: Response,
    limit: int = Query(100, ge=20, le=500),
    before_index: int | None = Query(None, ge=0),
    after_index: int | None = Query(None, ge=0),
    target_id: str = Query(""),
    target_date: str = Query(""),
    msg_type: str = Query("all"),
    family: str = Query("all"),
    sender: str = Query(""),
    keyword: str = Query(""),
    has_media: str = Query("all"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    _=Depends(verify_room_messages_password),
):
    """Return one chat-style chunk, newest chunk by default, older chunks by cursor."""
    response.headers["Cache-Control"] = "no-store"

    msg_type = msg_type.strip().upper()
    if msg_type == "":
        msg_type = "ALL"
    families = _parse_families(family)
    has_media = has_media.strip().lower()

    if has_media not in VALID_MEDIA_FILTERS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的媒体筛选")
    _validate_date("date_from", date_from)
    _validate_date("date_to", date_to)
    _validate_date("target_date", target_date)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="日期范围无效")
    if before_index is not None and after_index is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="消息游标无效")
    if target_id and target_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目标条件无效")

    rows, summary = _load_dataset()
    sender = sender.strip()
    keyword = keyword.strip()
    date_from = date_from.strip()
    date_to = date_to.strip()
    target_id = target_id.strip()
    target_date = target_date.strip()

    if _is_unfiltered(
        msg_type=msg_type,
        families=families,
        sender=sender,
        keyword=keyword,
        has_media=has_media,
        date_from=date_from,
        date_to=date_to,
    ):
        total = len(rows)
        target_index = _target_index(rows, target_id, target_date)
        if target_id and target_index is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标消息不在当前筛选结果中")
        if target_date and target_index is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"当前筛选条件下没有 {target_date} 的消息")
        if target_date and target_index is not None:
            target_id = str(rows[target_index].get("id", ""))
        start, end = _chunk_bounds(total, limit, before_index, after_index, target_index)
        items = [_public_row(row) for row in rows[start:end]]
    else:
        filtered = _filter_rows(
            rows,
            msg_type=msg_type,
            families=families,
            sender=sender,
            keyword=keyword,
            has_media=has_media,
            date_from=date_from,
            date_to=date_to,
        )

        total = len(filtered)
        target_index = _target_index(filtered, target_id, target_date)
        if target_id and target_index is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标消息不在当前筛选结果中")
        if target_date and target_index is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"当前筛选条件下没有 {target_date} 的消息")
        if target_date and target_index is not None:
            target_id = str(filtered[target_index].get("id", ""))
        start, end = _chunk_bounds(total, limit, before_index, after_index, target_index)
        items = [_public_row(row) for row in filtered[start:end]]

    return {
        "items": items,
        "limit": limit,
        "total": total,
        "start_index": start,
        "end_index": end,
        "next_before_index": start,
        "next_after_index": end,
        "has_more_older": start > 0,
        "has_more_newer": end < total,
        "target_id": target_id,
        "target_found": bool(target_id),
        "target_date": target_date,
        "target_date_found": bool(target_date and target_id),
        "summary": summary,
        "type_counts": summary.get("type_counts", []),
        "family_counts": summary.get("family_counts", []),
        "refresh_interval_seconds": cfg.ROOM_MESSAGES_REFRESH_INTERVAL_SECONDS,
    }


@router.get("/summary")
def get_room_messages_summary(
    response: Response,
    _=Depends(verify_room_messages_password),
):
    """Return room message summary and type counts."""
    response.headers["Cache-Control"] = "no-store"
    _, summary = _load_dataset()
    return {
        "summary": summary,
        "type_counts": summary.get("type_counts", []),
        "family_counts": summary.get("family_counts", []),
        "refresh_interval_seconds": cfg.ROOM_MESSAGES_REFRESH_INTERVAL_SECONDS,
    }


@router.post("/ignore-latest-batch")
def ignore_latest_unreplied_gift_batch(
    response: Response,
    _=Depends(verify_room_messages_password),
):
    """Mark the current latest un-replied gift batch as ignored."""
    response.headers["Cache-Control"] = "no-store"
    with _ignore_lock:
        return _run_ignored_state_mutation(_ignore_latest_unreplied_gift_batch_once)


@router.post("/undo-ignore")
def undo_latest_ignored_gift_batch(
    response: Response,
    _=Depends(verify_room_messages_password),
):
    """Undo the most recently ignored gift batch."""
    response.headers["Cache-Control"] = "no-store"
    with _ignore_lock:
        return _run_ignored_state_mutation(_undo_latest_ignored_gift_batch_once)


def _run_ignored_state_mutation(mutation) -> dict[str, Any]:
    attempts = 1 if _ignore_direct_enabled() else max(1, int(cfg.ROOM_MESSAGES_IGNORE_GIT_RETRIES or 1))
    for attempt in range(attempts):
        previous_text: str | None = None
        try:
            _sync_ignored_state_before_mutation()
            _invalidate_cache()
            previous_text = _read_ignored_state_text()
            return mutation()
        except _IgnoreGitRaceError:
            _restore_ignored_state_from_git_best_effort()
            _invalidate_cache()
            if attempt < attempts - 1:
                continue
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="忽略状态刚刚被另一台服务器更新，请重试",
            )
        except _IgnoreDirectSyncError as exc:
            if previous_text is not None:
                _write_ignored_state_text(previous_text)
            _invalidate_cache()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"忽略状态同步到另一台服务器失败：{exc}",
            ) from exc
        except _IgnoreGitSyncError as exc:
            _restore_ignored_state_from_git_best_effort()
            _invalidate_cache()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"忽略状态同步到 GitHub 失败：{exc}",
            ) from exc

    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="忽略状态同步冲突，请重试")


def _ignore_latest_unreplied_gift_batch_once() -> dict[str, Any]:
    _, summary = _load_dataset()
    batch = summary.get("latest_unreplied_gift_batch") or {}
    gift_message_ids = [str(item) for item in batch.get("gift_message_ids") or [] if item]
    if not gift_message_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前没有可忽略的未回复礼物")

    state = _load_ignored_state()
    ignored_ids = _ignored_gift_ids(state)
    if set(gift_message_ids).issubset(ignored_ids):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="这批礼物已经被忽略")

    ignored_batches = _ignored_batches(state)
    ignored_batch = {
        "batch_id": _batch_id(batch),
        "ignored_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_message_id": batch.get("start_message_id", ""),
        "start_bj_time": batch.get("start_bj_time", ""),
        "end_message_id": batch.get("end_message_id", ""),
        "end_bj_time": batch.get("end_bj_time", ""),
        "count": len(gift_message_ids),
        "gift_message_ids": gift_message_ids,
    }
    ignored_batches.append(ignored_batch)
    _write_ignored_state({"version": 1, "ignored_batches": ignored_batches})
    _persist_ignored_state_after_mutation(f"Ignore room message gift batch {ignored_batch['batch_id']}")
    _invalidate_cache()
    _, new_summary = _load_dataset()
    return _summary_payload(new_summary) | {"ignored_batch": ignored_batch}


def _undo_latest_ignored_gift_batch_once() -> dict[str, Any]:
    state = _load_ignored_state()
    ignored_batches = _ignored_batches(state)
    if not ignored_batches:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前没有可撤销的忽略记录")
    undone_batch = ignored_batches.pop()
    _write_ignored_state({"version": 1, "ignored_batches": ignored_batches})
    _persist_ignored_state_after_mutation(f"Undo room message gift batch {undone_batch.get('batch_id', '')}")
    _invalidate_cache()
    _, new_summary = _load_dataset()
    return _summary_payload(new_summary) | {"undone_batch": undone_batch}


def _data_path() -> Path:
    return Path(cfg.ROOM_MESSAGES_CSV_PATH)


def _ignore_path() -> Path:
    return Path(cfg.ROOM_MESSAGES_IGNORE_PATH)


def _ignore_git_enabled() -> bool:
    return bool(cfg.ROOM_MESSAGES_IGNORE_GIT_SYNC and _ignore_git_relpath())


def _ignore_git_relpath() -> str:
    try:
        return _ignore_path().resolve().relative_to(Path(cfg.PROJECT_ROOT).resolve()).as_posix()
    except ValueError:
        return ""


def _ignore_direct_enabled() -> bool:
    return bool(cfg.ROOM_MESSAGES_IGNORE_DIRECT_SYNC and cfg.ROOM_MESSAGES_IGNORE_DIRECT_PEER.strip())


def _sync_ignored_state_before_mutation() -> None:
    if _ignore_direct_enabled():
        _sync_ignored_state_from_peer()
    elif _ignore_git_enabled():
        _sync_ignored_state_from_git()


def _persist_ignored_state_after_mutation(message: str) -> None:
    if _ignore_direct_enabled():
        _push_ignored_state_to_peer()
    elif _ignore_git_enabled():
        _commit_ignored_state_to_git(message)


def _sync_ignored_state_from_peer() -> None:
    remote_text = _read_peer_ignored_state_text()
    remote_state = _normalise_ignored_state_text(remote_text)
    local_state = _load_ignored_state()

    if _ignored_state_fingerprint(remote_state) == _ignored_state_fingerprint(local_state):
        return

    if _ignored_state_updated_score(remote_state) >= _ignored_state_updated_score(local_state):
        _write_ignored_state_text(remote_text)
    else:
        _push_ignored_state_to_peer()


def _read_peer_ignored_state_text() -> str:
    remote_path = shlex.quote(cfg.ROOM_MESSAGES_IGNORE_DIRECT_PATH)
    empty_state = shlex.quote(_empty_ignored_state_text().rstrip("\n"))
    command = f"if [ -f {remote_path} ]; then cat {remote_path}; else printf '%s\\n' {empty_state}; fi"
    result = _direct_ssh(command)
    content = result.stdout or ""
    _normalise_ignored_state_text(content)
    return content if content.endswith("\n") else content + "\n"


def _push_ignored_state_to_peer() -> None:
    content = _read_ignored_state_text()
    _normalise_ignored_state_text(content)
    remote_path_raw = cfg.ROOM_MESSAGES_IGNORE_DIRECT_PATH
    remote_dir_raw = posixpath.dirname(remote_path_raw) or "."
    remote_path = shlex.quote(remote_path_raw)
    remote_dir = shlex.quote(remote_dir_raw)
    tmp_template = shlex.quote(posixpath.join(remote_dir_raw, ".room_messages_ignored_batches.XXXXXX"))
    command = (
        "set -e; "
        f"umask 077; mkdir -p {remote_dir}; "
        f"tmp=$(mktemp {tmp_template}); "
        'cat > "$tmp"; '
        f"mv \"$tmp\" {remote_path}"
    )
    _direct_ssh(command, input_text=content)


def _direct_ssh(command: str, *, input_text: str | None = None) -> subprocess.CompletedProcess:
    cmd = [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "LogLevel=ERROR",
        "-o",
        f"ConnectTimeout={cfg.ROOM_MESSAGES_IGNORE_DIRECT_CONNECT_TIMEOUT_SECONDS}",
        cfg.ROOM_MESSAGES_IGNORE_DIRECT_PEER.strip(),
        command,
    ]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=cfg.ROOM_MESSAGES_IGNORE_DIRECT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise _IgnoreDirectSyncError("SSH 操作超时") from exc
    if result.returncode != 0:
        raise _IgnoreDirectSyncError(_short_process_error(result))
    return result


def _sync_ignored_state_from_git() -> None:
    if not _ignore_git_enabled():
        return

    relpath = _ignore_git_relpath()
    remote = cfg.ROOM_MESSAGES_IGNORE_GIT_REMOTE
    branch = cfg.ROOM_MESSAGES_IGNORE_GIT_BRANCH
    remote_ref = f"{remote}/{branch}"
    _git(["fetch", remote, branch])
    latest = _git(["show", f"{remote_ref}:{relpath}"], check=False)
    if latest.returncode == 0:
        _write_ignored_state_text(latest.stdout or "")
    elif not _ignore_path().exists():
        _write_ignored_state({"version": 1, "ignored_batches": []})


def _commit_ignored_state_to_git(message: str) -> None:
    if not _ignore_git_enabled():
        return

    relpath = _ignore_git_relpath()
    remote = cfg.ROOM_MESSAGES_IGNORE_GIT_REMOTE
    branch = cfg.ROOM_MESSAGES_IGNORE_GIT_BRANCH
    remote_ref = f"{remote}/{branch}"
    _git(["fetch", remote, branch])

    with tempfile.TemporaryDirectory(prefix="room-messages-git-index-") as tmp:
        env = _git_env()
        env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
        _git(["read-tree", remote_ref], env=env)
        _git(["add", "--", relpath], env=env)
        if _git(["diff", "--cached", "--quiet", "--", relpath], check=False, env=env).returncode == 0:
            return
        tree = _git_output(["write-tree"], env=env).strip()
        parent = _git_output(["rev-parse", remote_ref]).strip()
        commit = _git_output(["commit-tree", tree, "-p", parent, "-m", message], env=env).strip()

    push = _git(["push", remote, f"{commit}:refs/heads/{branch}"], check=False)
    if push.returncode != 0:
        stderr = (push.stderr or "").strip()
        if "fetch first" in stderr or "non-fast-forward" in stderr or "stale info" in stderr:
            raise _IgnoreGitRaceError("GitHub 上已有更新")
        raise _IgnoreGitSyncError(_short_git_error(push))

    _git(["update-ref", f"refs/remotes/{remote}/{branch}", commit])
    current_branch = _git_output(["rev-parse", "--abbrev-ref", "HEAD"], check=False).strip()
    can_fast_forward = _git(["merge-base", "--is-ancestor", "HEAD", commit], check=False).returncode == 0
    if current_branch == branch and can_fast_forward:
        _git(["update-ref", f"refs/heads/{branch}", commit])
        _git(["reset", "-q", "--", relpath])


def _restore_ignored_state_from_git_best_effort() -> None:
    if not _ignore_git_enabled():
        return
    relpath = _ignore_git_relpath()
    remote_ref = f"{cfg.ROOM_MESSAGES_IGNORE_GIT_REMOTE}/{cfg.ROOM_MESSAGES_IGNORE_GIT_BRANCH}"
    try:
        latest = _git(["show", f"{remote_ref}:{relpath}"], check=False)
        if latest.returncode == 0:
            _write_ignored_state_text(latest.stdout or "")
    except _IgnoreGitSyncError:
        return


def _git(args: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(cfg.PROJECT_ROOT), *args]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=cfg.ROOM_MESSAGES_IGNORE_GIT_TIMEOUT_SECONDS,
            env=env or _git_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise _IgnoreGitSyncError("Git 操作超时") from exc
    if check and result.returncode != 0:
        raise _IgnoreGitSyncError(_short_git_error(result))
    return result


def _git_output(args: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> str:
    return _git(args, check=check, env=env).stdout or ""


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_AUTHOR_NAME", "SNH48 Room Messages Bot")
    env.setdefault("GIT_AUTHOR_EMAIL", "room-messages-bot@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    return env


def _short_git_error(result: subprocess.CompletedProcess) -> str:
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    return stderr or stdout or f"git exited {result.returncode}"


def _short_process_error(result: subprocess.CompletedProcess) -> str:
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    return stderr or stdout or f"command exited {result.returncode}"


def _load_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global _cache_mtime_ns, _cache_ignore_mtime_ns, _cache_rows, _cache_summary

    path = _data_path()
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="房间消息数据未生成")

    stat = path.stat()
    ignore_mtime_ns = _ignore_mtime_ns()
    if _cache_mtime_ns == stat.st_mtime_ns and _cache_ignore_mtime_ns == ignore_mtime_ns:
        return _cache_rows, _cache_summary

    with _cache_lock:
        stat = path.stat()
        ignore_mtime_ns = _ignore_mtime_ns()
        if _cache_mtime_ns == stat.st_mtime_ns and _cache_ignore_mtime_ns == ignore_mtime_ns:
            return _cache_rows, _cache_summary

        rows: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    normalised = _normalise_row(row)
                    normalised["_row_index"] = len(rows)
                    rows.append(normalised)
        except OSError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="房间消息数据读取失败") from exc

        _attach_message_links(rows)
        ignored_state = _load_ignored_state()
        ignored_ids = _ignored_gift_ids(ignored_state)
        _attach_ignored_gifts(rows, ignored_ids)
        summary = _build_summary(rows, stat.st_mtime, ignored_state)
        _cache_mtime_ns = stat.st_mtime_ns
        _cache_ignore_mtime_ns = ignore_mtime_ns
        _cache_rows = rows
        _cache_summary = summary
        return _cache_rows, _cache_summary


def _normalise_row(row: dict[str, str]) -> dict[str, Any]:
    msg_type = row.get("msg_type", "")
    family = TYPE_FAMILIES.get(msg_type, "event")
    parsed = _parse_content(row)
    media_url = parsed.get("media_url") or row.get("media_url", "")
    media_kind = parsed.get("media_kind") or _media_kind_for_type(msg_type)
    media_url = _resolve_media_url(str(media_url), media_kind)

    search_text = " ".join(
        str(value)
        for value in (
            row.get("bj_time", ""),
            row.get("msg_type", ""),
            row.get("sender_name", ""),
            row.get("sender_id", ""),
            row.get("text_content", ""),
            row.get("reply_text", ""),
            row.get("gift_name", ""),
            parsed.get("title", ""),
            parsed.get("body", ""),
            parsed.get("quote", ""),
            parsed.get("detail", ""),
        )
        if value
    ).lower()

    return {
        "id": row.get("id", ""),
        "server_id": row.get("server_id", ""),
        "bj_time": row.get("bj_time", ""),
        "date": row.get("bj_time", "")[:10],
        "msg_type": msg_type,
        "type_label": TYPE_LABELS.get(msg_type, msg_type or "未知"),
        "family": family,
        "sender_name": row.get("sender_name", ""),
        "sender_id": row.get("sender_id", ""),
        "reply_to_id": row.get("reply_to_id", ""),
        "reply_text": row.get("reply_text", ""),
        "gift_name": row.get("gift_name", ""),
        "gift_count": _to_int(row.get("gift_count"), 0),
        "gift_score": row.get("gift_score", ""),
        "media_url": media_url,
        "media_kind": media_kind,
        "media_path": row.get("media_path", ""),
        "meta_path": row.get("meta_path", ""),
        "jsonl_lineno": _to_int(row.get("jsonl_lineno"), 0),
        "title": parsed.get("title", ""),
        "body": parsed.get("body", ""),
        "quote": parsed.get("quote", ""),
        "detail": parsed.get("detail", ""),
        "action_url": _safe_http_url(str(parsed.get("action_url", ""))),
        "raw_content": row.get("text_content", ""),
        "_search_text": search_text,
    }


def _parse_content(row: dict[str, str]) -> dict[str, str]:
    msg_type = row.get("msg_type", "")
    raw = row.get("text_content", "")
    data = _loads_json(raw)

    if msg_type == "TEXT":
        return {"title": "文本消息", "body": raw}

    if msg_type == "REPLY":
        info = data.get("replyInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": f"回复 {info.get('replyName', '')}".strip(),
            "body": str(info.get("text") or raw),
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
        }

    if msg_type == "AUDIO_REPLY":
        info = data.get("replyInfo", {}) if isinstance(data, dict) else {}
        duration = _to_int(info.get("duration"), 0)
        return {
            "title": f"语音回复 {info.get('replyName', '')}".strip(),
            "body": f"语音回复 {duration} 秒" if duration else "语音回复",
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
            "media_url": str(info.get("voiceUrl") or ""),
            "media_kind": "audio",
        }

    if msg_type == "GIFT_TEXT":
        parts = [row.get("gift_name", "礼物")]
        if row.get("gift_count"):
            parts.append(f"x {row.get('gift_count')}")
        return {
            "title": "送礼物",
            "body": " ".join(parts),
            "detail": f"分值 {row.get('gift_score')}" if row.get("gift_score") else "",
            "media_kind": "image",
        }

    if msg_type == "GIFTREPLY":
        info = data.get("giftReplyInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": "文字回礼物",
            "body": str(info.get("text") or raw),
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
        }

    if msg_type == "AUDIO_GIFT_REPLY":
        info = data.get("giftReplyInfo", {}) if isinstance(data, dict) else {}
        duration = _to_int(info.get("duration"), 0)
        return {
            "title": "语音回礼物",
            "body": f"语音回礼 {duration} 秒" if duration else "语音回礼",
            "quote": str(info.get("replyText") or row.get("reply_text", "")),
            "media_url": str(info.get("voiceUrl") or ""),
            "media_kind": "audio",
        }

    if msg_type in {"AUDIO", "IMAGE", "VIDEO"}:
        duration_ms = _to_int(data.get("dur") if isinstance(data, dict) else 0, 0)
        duration = round(duration_ms / 1000) if duration_ms > 1000 else duration_ms
        title = TYPE_LABELS.get(msg_type, msg_type)
        detail_parts = []
        if isinstance(data, dict):
            if data.get("w") and data.get("h"):
                detail_parts.append(f"{data.get('w')} x {data.get('h')}")
            if duration:
                detail_parts.append(f"{duration} 秒")
        return {
            "title": title,
            "body": title,
            "detail": " · ".join(detail_parts),
            "media_kind": _media_kind_for_type(msg_type),
        }

    if msg_type == "EXPRESSIMAGE":
        info = data.get("expressImgInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": "表情包",
            "body": "表情包",
            "detail": _size_detail(info),
            "media_kind": "image",
        }

    if msg_type == "LIVEPUSH":
        info = data.get("livePushInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": str(info.get("liveTitle") or "直播推送"),
            "body": f"直播 ID {info.get('liveId')}" if info.get("liveId") else "直播推送",
            "action_url": str(info.get("shortPath") or ""),
            "media_kind": "image",
        }

    if msg_type.startswith("FLIPCARD"):
        info = data.get("filpCardInfo", {}) if isinstance(data, dict) else {}
        answer = info.get("answer", "")
        answer_data = _loads_json(answer) if isinstance(answer, str) else {}
        media_url = answer_data.get("url", "") if isinstance(answer_data, dict) else ""
        media_kind = "audio" if msg_type == "FLIPCARD_AUDIO" else "video" if msg_type == "FLIPCARD_VIDEO" else ""
        duration = _to_int(answer_data.get("duration") if isinstance(answer_data, dict) else 0, 0)
        return {
            "title": TYPE_LABELS.get(msg_type, "翻牌"),
            "body": str(answer if msg_type == "FLIPCARD" else f"{TYPE_LABELS.get(msg_type, '翻牌')} {duration} 秒").strip(),
            "quote": str(info.get("question") or ""),
            "detail": f"问题 ID {info.get('questionId')}" if info.get("questionId") else "",
            "media_url": str(media_url),
            "media_kind": media_kind,
        }

    if msg_type == "SHARE_POSTS":
        info = data.get("shareInfo", {}) if isinstance(data, dict) else {}
        return {
            "title": str(info.get("shareTitle") or "动态分享"),
            "body": str(info.get("shareDesc") or ""),
            "media_url": str(info.get("sharePic") or ""),
            "media_kind": "image",
            "action_url": str(info.get("jumpPath") or ""),
        }

    if msg_type == "RED_PACKET_2026":
        return {
            "title": "红包",
            "body": str(data.get("blessMessage") or "红包消息") if isinstance(data, dict) else raw,
            "detail": f"来自 {data.get('creatorName')}" if isinstance(data, dict) and data.get("creatorName") else "",
            "media_url": str(data.get("coverUrl") or "") if isinstance(data, dict) else "",
            "media_kind": "image",
        }

    return {"title": TYPE_LABELS.get(msg_type, msg_type), "body": raw}


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    msg_type: str,
    families: set[str] | None,
    sender: str,
    keyword: str,
    has_media: str,
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    sender_lower = sender.lower()
    keyword_lower = keyword.lower()
    filtered: list[dict[str, Any]] = []

    for row in rows:
        if msg_type != "ALL" and row["msg_type"] != msg_type:
            continue
        if families is not None and row["family"] not in families:
            continue
        if sender_lower and sender_lower not in row["sender_name"].lower():
            continue
        if keyword_lower and keyword_lower not in row["_search_text"]:
            continue
        if has_media == "with" and not row["media_url"] and not row["media_path"]:
            continue
        if has_media == "without" and (row["media_url"] or row["media_path"]):
            continue
        if date_from and row["date"] < date_from:
            continue
        if date_to and row["date"] > date_to:
            continue
        filtered.append(row)
    return filtered


def _is_unfiltered(
    *,
    msg_type: str,
    families: set[str] | None,
    sender: str,
    keyword: str,
    has_media: str,
    date_from: str,
    date_to: str,
) -> bool:
    return (
        msg_type == "ALL"
        and families is None
        and not sender
        and not keyword
        and has_media == "all"
        and not date_from
        and not date_to
    )


def _parse_families(value: str) -> set[str] | None:
    parts = {part.strip().lower() for part in (value or "all").split(",") if part.strip()}
    if not parts or "all" in parts:
        return None
    invalid = parts - VALID_FAMILIES
    if invalid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的消息分组")
    return parts


def _chunk_bounds(
    total: int,
    limit: int,
    before_index: int | None,
    after_index: int | None,
    target_index: int | None,
) -> tuple[int, int]:
    if target_index is not None:
        end = min(total, target_index + 1)
        return max(0, end - limit), end
    if after_index is not None:
        start = min(after_index, total)
        return start, min(total, start + limit)
    end = total if before_index is None else min(before_index, total)
    return max(0, end - limit), end


def _find_row_index(rows: list[dict[str, Any]], message_id: str) -> int | None:
    if not message_id:
        return None
    for idx, row in enumerate(rows):
        if row.get("id") == message_id:
            return idx
    return None


def _find_date_index(rows: list[dict[str, Any]], target_date: str) -> int | None:
    if not target_date:
        return None
    for idx, row in enumerate(rows):
        if row.get("date") == target_date:
            return idx
    return None


def _target_index(rows: list[dict[str, Any]], target_id: str, target_date: str) -> int | None:
    if target_id:
        return _find_row_index(rows, target_id)
    if target_date:
        return _find_date_index(rows, target_date)
    return None


def _attach_message_links(rows: list[dict[str, Any]]) -> None:
    rows_by_id = {str(row.get("id", "")): row for row in rows if row.get("id")}
    reply_ids_by_gift: dict[str, list[str]] = {}
    for row in rows:
        reply_to_id = str(row.get("reply_to_id", ""))
        if reply_to_id and reply_to_id in rows_by_id:
            row["reply_target"] = _reply_target(rows_by_id[reply_to_id])
        if row.get("family") == "gift_reply" and row.get("reply_to_id") and row.get("id"):
            reply_ids_by_gift.setdefault(str(row["reply_to_id"]), []).append(str(row["id"]))

    for row in rows:
        if row.get("family") == "gift":
            reply_ids = reply_ids_by_gift.get(str(row.get("id", "")), [])
            row["reply_message_ids"] = reply_ids
            row["reply_count"] = len(reply_ids)
        elif row.get("family") == "gift_reply":
            row["gift_message_id"] = row.get("reply_to_id", "")


def _attach_ignored_gifts(rows: list[dict[str, Any]], ignored_ids: set[str]) -> None:
    for row in rows:
        if row.get("family") == "gift":
            row["ignored"] = str(row.get("id", "")) in ignored_ids


def _ignore_mtime_ns() -> int:
    path = _ignore_path()
    if not path.exists():
        return -1
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return -1


def _empty_ignored_state_text() -> str:
    return json.dumps({"version": 1, "ignored_batches": []}, ensure_ascii=False) + "\n"


def _read_ignored_state_text() -> str:
    path = _ignore_path()
    if not path.exists():
        return _empty_ignored_state_text()
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return _empty_ignored_state_text()
    _normalise_ignored_state_text(content)
    return content if content.endswith("\n") else content + "\n"


def _normalise_ignored_state_text(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise _IgnoreDirectSyncError("忽略状态 JSON 无效") from exc
    if not isinstance(data, dict):
        raise _IgnoreDirectSyncError("忽略状态不是对象")
    batches = data.get("ignored_batches")
    if not isinstance(batches, list):
        data["ignored_batches"] = []
    return data


def _ignored_state_fingerprint(state: dict[str, Any]) -> str:
    payload = {"ignored_batches": _ignored_batches(state)}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ignored_state_updated_score(state: dict[str, Any]) -> float:
    value = str(state.get("updated_at") or "")
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return 0.0


def _load_ignored_state() -> dict[str, Any]:
    path = _ignore_path()
    if not path.exists():
        return {"version": 1, "ignored_batches": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "ignored_batches": []}
    if not isinstance(data, dict):
        return {"version": 1, "ignored_batches": []}
    batches = data.get("ignored_batches")
    if not isinstance(batches, list):
        data["ignored_batches"] = []
    return data


def _write_ignored_state(state: dict[str, Any]) -> None:
    path = _ignore_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ignored_batches": _ignored_batches(state),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_ignored_state_text(content: str) -> None:
    path = _ignore_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    tmp.replace(path)


def _ignored_batches(state: dict[str, Any]) -> list[dict[str, Any]]:
    batches = state.get("ignored_batches")
    if not isinstance(batches, list):
        return []
    return [batch for batch in batches if isinstance(batch, dict)]


def _ignored_gift_ids(state: dict[str, Any]) -> set[str]:
    ignored: set[str] = set()
    for batch in _ignored_batches(state):
        for message_id in batch.get("gift_message_ids") or []:
            if message_id:
                ignored.add(str(message_id))
    return ignored


def _latest_ignored_batch(state: dict[str, Any]) -> dict[str, Any]:
    batches = _ignored_batches(state)
    if not batches:
        return _empty_ignored_batch()
    batch = batches[-1]
    gift_ids = [str(item) for item in batch.get("gift_message_ids") or [] if item]
    return {
        "batch_id": batch.get("batch_id", ""),
        "ignored_at": batch.get("ignored_at", ""),
        "start_message_id": batch.get("start_message_id", ""),
        "start_bj_time": batch.get("start_bj_time", ""),
        "end_message_id": batch.get("end_message_id", ""),
        "end_bj_time": batch.get("end_bj_time", ""),
        "count": len(gift_ids) if gift_ids else int(batch.get("count") or 0),
        "gift_message_ids": gift_ids,
    }


def _empty_ignored_batch() -> dict[str, Any]:
    return {
        "batch_id": "",
        "ignored_at": "",
        "start_message_id": "",
        "start_bj_time": "",
        "end_message_id": "",
        "end_bj_time": "",
        "count": 0,
        "gift_message_ids": [],
    }


def _batch_id(batch: dict[str, Any]) -> str:
    return f"{batch.get('start_message_id', '')}:{batch.get('end_message_id', '')}"


def _invalidate_cache() -> None:
    global _cache_mtime_ns, _cache_ignore_mtime_ns
    _cache_mtime_ns = -1
    _cache_ignore_mtime_ns = -2


def _summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": summary,
        "type_counts": summary.get("type_counts", []),
        "family_counts": summary.get("family_counts", []),
        "refresh_interval_seconds": cfg.ROOM_MESSAGES_REFRESH_INTERVAL_SECONDS,
    }


def _reply_target(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "bj_time": row.get("bj_time", ""),
        "sender_name": row.get("sender_name", ""),
        "sender_id": row.get("sender_id", ""),
        "msg_type": row.get("msg_type", ""),
        "type_label": row.get("type_label", ""),
        "family": row.get("family", ""),
        "title": row.get("title", ""),
        "body": row.get("body", ""),
        "gift_name": row.get("gift_name", ""),
        "gift_count": row.get("gift_count", 0),
        "media_url": row.get("media_url", ""),
        "media_kind": row.get("media_kind", ""),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _build_summary(rows: list[dict[str, Any]], mtime: float, ignored_state: dict[str, Any]) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    for row in rows:
        type_counts[row["msg_type"]] = type_counts.get(row["msg_type"], 0) + 1
        family_counts[row["family"]] = family_counts.get(row["family"], 0) + 1
    ignored_batches = _ignored_batches(ignored_state)
    ignored_gift_ids = _ignored_gift_ids(ignored_state)

    return {
        "total_messages": len(rows),
        "first_bj_time": rows[0]["bj_time"] if rows else "",
        "latest_bj_time": rows[-1]["bj_time"] if rows else "",
        "source_path": str(_data_path()),
        "source_mtime": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "type_kinds": len(type_counts),
        "ignored_batch_count": len(ignored_batches),
        "ignored_gift_count": len(ignored_gift_ids),
        "latest_ignored_batch": _latest_ignored_batch(ignored_state),
        "latest_unreplied_gift_batch": _latest_unreplied_gift_batch(rows),
        "type_counts": [
            {
                "msg_type": msg_type,
                "label": TYPE_LABELS.get(msg_type, msg_type),
                "family": TYPE_FAMILIES.get(msg_type, "event"),
                "count": count,
            }
            for msg_type, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "family_counts": [
            {"family": family, "label": _family_label(family), "count": count}
            for family, count in sorted(family_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _latest_unreplied_gift_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gift_rows = [row for row in rows if row.get("family") == "gift"]
    batch_end_index = None
    for idx in range(len(gift_rows) - 1, -1, -1):
        if _is_unreplied_gift(gift_rows[idx]):
            batch_end_index = idx
            break

    if batch_end_index is None:
        return {
            "start_message_id": "",
            "start_bj_time": "",
            "end_message_id": "",
            "end_bj_time": "",
            "count": 0,
            "gift_message_ids": [],
        }

    batch_start_index = batch_end_index
    while batch_start_index > 0 and _is_unreplied_gift(gift_rows[batch_start_index - 1]):
        batch_start_index -= 1

    start = gift_rows[batch_start_index]
    end = gift_rows[batch_end_index]
    return {
        "start_message_id": start.get("id", ""),
        "start_bj_time": start.get("bj_time", ""),
        "end_message_id": end.get("id", ""),
        "end_bj_time": end.get("bj_time", ""),
        "count": batch_end_index - batch_start_index + 1,
        "gift_message_ids": [str(row.get("id", "")) for row in gift_rows[batch_start_index : batch_end_index + 1] if row.get("id")],
    }


def _is_unreplied_gift(row: dict[str, Any]) -> bool:
    return row.get("family") == "gift" and int(row.get("reply_count") or 0) == 0 and not row.get("ignored")


def _loads_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip().startswith("{"):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _media_kind_for_type(msg_type: str) -> str:
    if msg_type in {"IMAGE", "EXPRESSIMAGE", "GIFT_TEXT", "LIVEPUSH", "SHARE_POSTS", "RED_PACKET_2026"}:
        return "image"
    if msg_type in {"AUDIO", "AUDIO_REPLY", "AUDIO_GIFT_REPLY", "FLIPCARD_AUDIO"}:
        return "audio"
    if msg_type in {"VIDEO", "FLIPCARD_VIDEO"}:
        return "video"
    return ""


def _resolve_media_url(value: str, media_kind: str) -> str:
    value = _safe_http_url(value)
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not value.startswith("/"):
        return ""
    if media_kind in {"audio", "video"}:
        return "https://mp4-new1.48.cn" + value
    return "https://source3.48.cn" + value


def _safe_http_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://") or value.startswith("/"):
        return value
    return ""


def _family_label(family: str) -> str:
    return {
        "text": "文本",
        "reply": "回复",
        "gift": "礼物",
        "gift_reply": "回礼物",
        "media": "媒体",
        "flipcard": "翻牌",
        "live": "直播",
        "share": "分享",
        "event": "事件",
    }.get(family, family)


def _size_detail(info: dict[str, Any]) -> str:
    if info.get("width") and info.get("height"):
        return f"{info.get('width')} x {info.get('height')}"
    if info.get("w") and info.get("h"):
        return f"{info.get('w')} x {info.get('h')}"
    return ""


def _validate_date(label: str, value: str) -> None:
    if value and not DATE_RE.match(value.strip()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{label} 日期格式应为 YYYY-MM-DD")


def _to_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

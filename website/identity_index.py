"""Shared cache for the pocket48 fan identity index.

The full index is used by the AI resolver and retains every historical
nickname.  Websites read the compact ``fan_identity_web.json`` instead: it only
maps ID -> latest name and name -> IDs, so it loads in ~0.15s / ~38MB instead of
~2.4s / ~134MB.  A single in-process parse keeps both consumers warm.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from website import config as cfg

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_signature: tuple[Any, ...] | None = None
_loaded = False
_warmup_started = False
_by_id: dict[str, dict[str, Any]] = {}
_by_name: dict[str, dict[str, Any]] = {}
_latest_by_id: dict[str, str] = {}
_generated_at = ""


def _clean(value: Any, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _path() -> Path:
    full = Path(cfg.REDBLUE_IDENTITY_INDEX_PATH)
    web_path = str(getattr(cfg, "REDBLUE_IDENTITY_WEB_PATH", "") or "")
    if web_path:
        web = Path(web_path)
        try:
            if web.exists() and (
                not full.exists()
                or web.stat().st_mtime_ns >= full.stat().st_mtime_ns
            ):
                return web
        except OSError:
            pass
    return full


def _file_signature(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
        return str(path), stat.st_mtime_ns, stat.st_size
    except OSError:
        return str(path), 0, 0


def _add(by_id: dict[str, dict[str, Any]], by_name: dict[str, dict[str, Any]], fan_id: str, name: str, seen: str = "") -> None:
    fan_id = _clean(fan_id, 32)
    name = _clean(name, 120)
    if not fan_id and not name:
        return
    if fan_id:
        account = by_id.setdefault(
            fan_id,
            {"fan_id": fan_id, "names": set(), "latest_name": "", "last_seen": ""},
        )
        if name:
            account["names"].add(name)
            if not seen or seen >= str(account.get("last_seen") or ""):
                account["latest_name"] = name
                account["last_seen"] = seen or account.get("last_seen") or ""
    if name:
        nick = by_name.setdefault(
            name,
            {"name": name, "ids": set(), "last_seen": ""},
        )
        if fan_id:
            nick["ids"].add(fan_id)
        if seen and seen >= str(nick.get("last_seen") or ""):
            nick["last_seen"] = seen


def _build_web(data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str], str]:
    by_id: dict[str, dict[str, Any]] = {}
    latest = data.get("latest")
    if isinstance(latest, dict):
        for fan_id, name in latest.items():
            fan_id = _clean(fan_id, 32)
            name = _clean(name, 120)
            if fan_id and name:
                by_id[fan_id] = {"fan_id": fan_id, "latest_name": name, "last_seen": ""}
    by_name: dict[str, dict[str, Any]] = {}
    names = data.get("names")
    if isinstance(names, dict):
        for name, values in names.items():
            name = _clean(name, 120)
            if not name:
                continue
            if isinstance(values, dict):
                values = values.get("ids")
            if not isinstance(values, (list, tuple, set)):
                continue
            ids = {_clean(item, 32) for item in values if _clean(item, 32)}
            if ids:
                by_name[name] = {"name": name, "ids": ids, "last_seen": ""}
    latest_by_id = {
        fan_id: str(account.get("latest_name") or "")
        for fan_id, account in by_id.items()
        if account.get("latest_name")
    }
    return by_id, by_name, latest_by_id, _clean(data.get("generated_at"), 40)


def _build(data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str], str]:
    generated_at = _clean(data.get("generated_at"), 40)
    if (
        isinstance(data.get("latest"), dict)
        and isinstance(data.get("names"), dict)
        and not isinstance(data.get("accounts"), dict)
    ):
        return _build_web(data)
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}

    accounts = data.get("accounts")
    if isinstance(accounts, dict):
        for fan_id, account in accounts.items():
            if not isinstance(account, dict):
                continue
            names = account.get("names")
            if isinstance(names, dict):
                for name, meta in names.items():
                    seen = _clean(meta.get("last_seen"), 32) if isinstance(meta, dict) else ""
                    _add(by_id, by_name, str(fan_id), str(name), seen)
            latest = _clean(account.get("latest_name"), 120)
            if latest:
                _add(by_id, by_name, str(fan_id), latest, _clean(account.get("last_seen"), 32))

    nicknames = data.get("nicknames")
    if isinstance(nicknames, dict):
        for name, meta in nicknames.items():
            if not isinstance(meta, dict):
                continue
            ids = meta.get("ids")
            if isinstance(ids, list):
                for fan_id in ids:
                    _add(by_id, by_name, str(fan_id), str(name), _clean(meta.get("last_seen"), 32))
            else:
                _add(by_id, by_name, "", str(name), _clean(meta.get("last_seen"), 32))

    latest_by_id = {
        fan_id: str(account.get("latest_name") or "")
        for fan_id, account in by_id.items()
        if account.get("latest_name")
    }
    return by_id, by_name, latest_by_id, generated_at


def _load() -> None:
    global _signature, _loaded, _by_id, _by_name, _latest_by_id, _generated_at

    path = _path()
    signature = _file_signature(path)
    with _lock:
        if _loaded and _signature == signature:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        by_id, by_name, latest_by_id, generated_at = _build(data)
        _by_id = by_id
        _by_name = by_name
        _latest_by_id = latest_by_id
        _generated_at = generated_at
        _signature = signature
        _loaded = True


def redblue_index() -> dict[str, Any]:
    """Return the by-id/by-name index used by the red-blue ledger."""
    _load()
    with _lock:
        return {
            "by_id": _by_id,
            "by_name": _by_name,
            "generated_at": _generated_at,
            "sources": [],
        }


def latest_names_by_id() -> dict[str, str]:
    """Return pocket48 fan ID -> latest display name."""
    _load()
    with _lock:
        return _latest_by_id


def clear_cache() -> None:
    global _signature, _loaded, _by_id, _by_name, _latest_by_id, _generated_at
    with _lock:
        _signature = None
        _loaded = False
        _by_id = {}
        _by_name = {}
        _latest_by_id = {}
        _generated_at = ""


def start_warmup() -> None:
    """Load the index in a daemon thread so the first request stays fast."""
    global _warmup_started
    with _lock:
        if _warmup_started:
            return
        _warmup_started = True
    threading.Thread(target=_warmup, name="identity-index-warmup", daemon=True).start()


def _warmup() -> None:
    try:
        _load()
    except Exception:
        logger.exception("身份索引后台预热失败")

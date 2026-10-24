"""All-member scoring board API.

Reads the derived ``score_board.json`` produced by the fan-hub Tencent
collection node and exposes password-protected, filterable rankings.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from website import config as cfg
from website.score_gifts_api import verify_score_gifts_password

router = APIRouter(prefix="/api/score-all-members", tags=["全员计分榜"])
BJ_TZ = timezone(timedelta(hours=8))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_SOURCES = {"all", "room", "live"}
VALID_SORTS = {"score_desc", "name_asc", "team_asc"}

_cache_lock = threading.Lock()
_cache_path = ""
_cache_mtime_ns = -1
_cache_doc: dict[str, Any] = {}


def _load_board() -> dict[str, Any]:
    global _cache_path, _cache_mtime_ns, _cache_doc
    path = Path(cfg.SCORE_ALL_MEMBERS_DATA_PATH)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="全员计分数据未生成")
    stat = path.stat()
    if _cache_path == str(path) and _cache_mtime_ns == stat.st_mtime_ns:
        return _cache_doc
    with _cache_lock:
        stat = path.stat()
        if _cache_path == str(path) and _cache_mtime_ns == stat.st_mtime_ns:
            return _cache_doc
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="全员计分数据读取失败") from exc
        if not isinstance(doc, dict):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="全员计分数据格式无效")
        _cache_path = str(path)
        _cache_mtime_ns = stat.st_mtime_ns
        _cache_doc = doc
        return _cache_doc


def _validate_date(name: str, value: str) -> None:
    if value and not DATE_RE.match(value):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{name} 日期格式无效")


def _season_key(board: dict[str, Any], requested: str) -> str:
    seasons = board.get("seasons") if isinstance(board.get("seasons"), dict) else {}
    season = (requested or "").strip()
    if season and season not in seasons:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的赛季")
    if season:
        return season
    latest = str(board.get("latest_season") or "")
    if latest in seasons:
        return latest
    return next(iter(seasons), "")


def _member_index(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in board.get("members") or []:
        if isinstance(item, dict) and item.get("member_id"):
            index[str(item["member_id"])] = item
    return index


def _filter_cells(
    board: dict[str, Any],
    *,
    season: str,
    group: str,
    team: str,
    member: str,
    gift_name: str,
    source: str,
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    group = group.strip()
    team = team.strip()
    member = member.strip().lower()
    gift_name = gift_name.strip()
    members = _member_index(board)
    cells: list[dict[str, Any]] = []
    for cell in board.get("cells") or []:
        if not isinstance(cell, dict) or cell.get("season") != season:
            continue
        meta = members.get(str(cell.get("member_id") or ""), {})
        cell_group = str(meta.get("group") or cell.get("group_name") or "")
        cell_team = str(meta.get("team") or "")
        if group and cell_group != group:
            continue
        if team and cell_team != team:
            continue
        if member:
            haystack = f"{meta.get('member_name') or cell.get('member_name') or ''} {cell.get('member_id') or ''}".lower()
            if member not in haystack:
                continue
        if gift_name and str(cell.get("gift_name") or "") != gift_name:
            continue
        cell_source = str(cell.get("source") or "")
        if source != "all" and cell_source != source:
            continue
        day = str(cell.get("date") or "")
        if date_from and day < date_from:
            continue
        if date_to and day > date_to:
            continue
        cells.append(cell)
    return cells


def _aggregate(
    board: dict[str, Any],
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    members = _member_index(board)
    by_member: dict[str, dict[str, Any]] = {}
    gift_distribution: dict[tuple[str, str], dict[str, Any]] = {}
    team_distribution: dict[tuple[str, str], dict[str, Any]] = {}
    daily_distribution: dict[str, dict[str, Any]] = {}

    for cell in cells:
        member_id = str(cell.get("member_id") or "")
        meta = members.get(member_id, {})
        member_name = str(meta.get("member_name") or cell.get("member_name") or member_id)
        group = str(meta.get("group") or cell.get("group_name") or "")
        team = str(meta.get("team") or "")
        team_lbl = str(meta.get("team_label") or team or "未分组")
        score = float(cell.get("score") or 0)
        count = int(cell.get("count") or 0)
        records = int(cell.get("records") or 0)
        source = str(cell.get("source") or "")
        gift_id = str(cell.get("gift_id") or "")
        gift_name = str(cell.get("gift_name") or "")

        row = by_member.setdefault(
            member_id,
            {
                "member_id": member_id,
                "member_name": member_name,
                "group": group,
                "team": team,
                "team_label": team_lbl,
                "period_name": str(meta.get("period_name") or ""),
                "status": str(meta.get("status") or ""),
                "total_score": 0.0,
                "room_score": 0.0,
                "live_score": 0.0,
                "total_count": 0,
                "records": 0,
                "gifts": {},
                "first_event_date": "",
                "latest_event_date": "",
            },
        )
        row["total_score"] += score
        row["room_score" if source == "room" else "live_score"] += score
        row["total_count"] += count
        row["records"] += records
        day = str(cell.get("date") or "")
        if day:
            row["first_event_date"] = min(filter(None, [row["first_event_date"], day]))
            row["latest_event_date"] = max(filter(None, [row["latest_event_date"], day]))
        gift_key = gift_id or gift_name
        gift = row["gifts"].setdefault(
            gift_key,
            {"gift_id": gift_id, "gift_name": gift_name, "score": 0.0, "count": 0, "records": 0},
        )
        gift["score"] += score
        gift["count"] += count
        gift["records"] += records

        gift_row = gift_distribution.setdefault(
            (gift_id, gift_name),
            {"gift_id": gift_id, "gift_name": gift_name, "score": 0.0, "count": 0, "records": 0, "members": set()},
        )
        gift_row["score"] += score
        gift_row["count"] += count
        gift_row["records"] += records
        gift_row["members"].add(member_id)

        team_key = (group, team or team_lbl)
        team_row = team_distribution.setdefault(
            team_key,
            {"group": group, "team": team, "team_label": team_lbl, "score": 0.0, "count": 0, "members": set()},
        )
        team_row["score"] += score
        team_row["count"] += count
        team_row["members"].add(member_id)

        if day:
            daily = daily_distribution.setdefault(day, {"date": day, "score": 0.0, "count": 0, "records": 0})
            daily["score"] += score
            daily["count"] += count
            daily["records"] += records

    member_rows: list[dict[str, Any]] = []
    for row in by_member.values():
        gifts = sorted(row["gifts"].values(), key=lambda item: (-float(item["score"]), str(item["gift_name"])))
        row["gifts"] = gifts
        row["total_score"] = round(float(row["total_score"]), 6)
        row["room_score"] = round(float(row["room_score"]), 6)
        row["live_score"] = round(float(row["live_score"]), 6)
        member_rows.append(row)

    gift_rows = []
    for row in gift_distribution.values():
        item = dict(row)
        item["members"] = len(row["members"])
        item["score"] = round(float(item["score"]), 6)
        gift_rows.append(item)
    gift_rows.sort(key=lambda item: (-float(item["score"]), str(item["gift_name"])))

    team_rows = []
    for row in team_distribution.values():
        item = dict(row)
        item["members"] = len(row["members"])
        item["score"] = round(float(item["score"]), 6)
        team_rows.append(item)
    team_rows.sort(key=lambda item: (-float(item["score"]), str(item["group"]), str(item["team_label"])))

    daily_rows = sorted(daily_distribution.values(), key=lambda item: item["date"])
    for item in daily_rows:
        item["score"] = round(float(item["score"]), 6)

    room_score = sum(float(row["room_score"]) for row in member_rows)
    live_score = sum(float(row["live_score"]) for row in member_rows)
    total_score = sum(float(row["total_score"]) for row in member_rows)
    return {
        "summary": {
            "total_score": round(total_score, 6),
            "room_score": round(room_score, 6),
            "live_score": round(live_score, 6),
            "total_count": sum(int(row["total_count"]) for row in member_rows),
            "records": sum(int(row["records"]) for row in member_rows),
            "members": len(member_rows),
            "gift_kinds": len(gift_rows),
            "first_event_date": min((row["first_event_date"] for row in member_rows if row["first_event_date"]), default=""),
            "latest_event_date": max((row["latest_event_date"] for row in member_rows if row["latest_event_date"]), default=""),
        },
        "members": member_rows,
        "gift_distribution": gift_rows,
        "team_distribution": team_rows,
        "daily_distribution": daily_rows,
    }


def _facets(board: dict[str, Any], season: str) -> dict[str, Any]:
    members = _member_index(board)
    groups: set[str] = set()
    teams: dict[tuple[str, str], dict[str, str]] = {}
    member_ids: set[str] = set()
    gift_keys: set[str] = set()
    for cell in board.get("cells") or []:
        if not isinstance(cell, dict) or cell.get("season") != season:
            continue
        member_id = str(cell.get("member_id") or "")
        if not member_id:
            continue
        member_ids.add(member_id)
        meta = members.get(member_id, {})
        group = str(meta.get("group") or cell.get("group_name") or "")
        team = str(meta.get("team") or "")
        if group:
            groups.add(group)
        if team:
            teams[(group, team)] = {
                "group": group,
                "team": team,
                "team_label": str(meta.get("team_label") or team),
            }
        gift_keys.add(str(cell.get("gift_id") or cell.get("gift_name") or ""))
    gifts = []
    for entry in board.get("gift_authority") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("gift_id") or entry.get("gift_name") or "")
        if key not in gift_keys:
            continue
        seasons = entry.get("seasons") if isinstance(entry.get("seasons"), list) else []
        if seasons and season not in seasons:
            continue
        gifts.append(entry)
    return {
        "groups": sorted(groups),
        "teams": sorted(teams.values(), key=lambda item: (item["group"], item["team"])),
        "gifts": gifts,
        "members": len(member_ids),
    }


def _season_meta(board: dict[str, Any], season: str) -> dict[str, Any]:
    seasons = board.get("seasons") if isinstance(board.get("seasons"), dict) else {}
    meta = seasons.get(season) if isinstance(seasons.get(season), dict) else {}
    coverage = board.get("coverage") if isinstance(board.get("coverage"), dict) else {}
    season_coverage = (coverage.get("seasons") or {}).get(season) if isinstance(coverage.get("seasons"), dict) else {}
    return {
        "season": meta,
        "coverage": season_coverage or {},
        "archive_coverage": {
            "room_archive_first_date": coverage.get("room_archive_first_date", ""),
            "room_archive_latest_date": coverage.get("room_archive_latest_date", ""),
            "live_archive_first_date": coverage.get("live_archive_first_date", ""),
            "live_archive_latest_date": coverage.get("live_archive_latest_date", ""),
        },
    }


@router.get("/verify")
def verify_score_all_members_login(
    response: Response,
    _=Depends(verify_score_gifts_password),
):
    response.headers["Cache-Control"] = "no-store"
    return {"verified": True}


@router.get("/summary")
def get_score_all_members_summary(
    response: Response,
    season: str = Query(""),
    _=Depends(verify_score_gifts_password),
):
    response.headers["Cache-Control"] = "no-store"
    board = _load_board()
    key = _season_key(board, season)
    meta = _season_meta(board, key)
    return {
        "generated_at": str(board.get("generated_at", "")),
        "timezone": str(board.get("timezone", "Asia/Shanghai")),
        "season": key,
        "seasons": board.get("seasons", {}),
        "latest_season": board.get("latest_season", ""),
        "coverage": meta["coverage"],
        "archive_coverage": meta["archive_coverage"],
        "gift_authority": board.get("gift_authority", []),
        "facets": _facets(board, key),
    }


@router.get("/data")
def get_score_all_members_data(
    response: Response,
    season: str = Query(""),
    group: str = Query(""),
    team: str = Query(""),
    member: str = Query(""),
    gift_name: str = Query(""),
    source: str = Query("all"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sort: str = Query("score_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    _=Depends(verify_score_gifts_password),
):
    response.headers["Cache-Control"] = "no-store"
    source = source.strip().lower()
    sort = sort.strip().lower()
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的数据来源")
    if sort not in VALID_SORTS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的排序方式")
    _validate_date("date_from", date_from)
    _validate_date("date_to", date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="日期范围无效")

    board = _load_board()
    key = _season_key(board, season)
    cells = _filter_cells(
        board,
        season=key,
        group=group,
        team=team,
        member=member,
        gift_name=gift_name,
        source=source,
        date_from=date_from,
        date_to=date_to,
    )
    aggregated = _aggregate(board, cells)
    rows = aggregated["members"]
    if sort == "name_asc":
        rows.sort(key=lambda item: (str(item["group"]), str(item["team"]), str(item["member_name"])))
    elif sort == "team_asc":
        rows.sort(key=lambda item: (str(item["group"]), str(item["team"]), -float(item["total_score"]), str(item["member_name"])))
    else:
        rows.sort(key=lambda item: (-float(item["total_score"]), str(item["member_name"])))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    meta = _season_meta(board, key)
    return {
        "generated_at": str(board.get("generated_at", "")),
        "timezone": str(board.get("timezone", "Asia/Shanghai")),
        "season": key,
        "seasons": board.get("seasons", {}),
        "latest_season": board.get("latest_season", ""),
        "coverage": meta["coverage"],
        "archive_coverage": meta["archive_coverage"],
        "gift_authority": board.get("gift_authority", []),
        "facets": _facets(board, key),
        "summary": aggregated["summary"],
        "members": rows[start:end],
        "gift_distribution": aggregated["gift_distribution"],
        "team_distribution": aggregated["team_distribution"],
        "daily_distribution": aggregated["daily_distribution"],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }

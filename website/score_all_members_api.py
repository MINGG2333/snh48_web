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
VALID_SOURCES = {"all", "room", "live", "gnz", "xox", "third_party"}
VALID_SORTS = {"score_desc", "name_asc", "team_asc"}
VALID_QUALIFICATIONS = {"all", "qualified", "not_qualified", "not_participant"}
QUALIFICATION_FILENAME = "redblue_stage1_qualification.json"
OFFICIAL_TEAMS_FILENAME = "official_member_teams.json"

_cache_lock = threading.Lock()
_cache_path = ""
_cache_mtime_ns = -1
_cache_overlay_mtime_ns = -1
_cache_qualification_mtime_ns = -1
_cache_official_teams_mtime_ns = -1
_cache_doc: dict[str, Any] = {}


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _load_board() -> dict[str, Any]:
    global _cache_path, _cache_mtime_ns, _cache_overlay_mtime_ns
    global _cache_qualification_mtime_ns, _cache_official_teams_mtime_ns, _cache_doc
    path = Path(cfg.SCORE_ALL_MEMBERS_DATA_PATH)
    overlay_path = path.parent / "realtime_cells.json"
    qualification_path = path.parent / QUALIFICATION_FILENAME
    official_teams_path = path.parent / OFFICIAL_TEAMS_FILENAME
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="全员计分数据未生成")

    def _mtime(candidate: Path) -> int:
        return candidate.stat().st_mtime_ns if candidate.exists() else 0

    stat = path.stat()
    overlay_mtime = _mtime(overlay_path)
    qualification_mtime = _mtime(qualification_path)
    official_teams_mtime = _mtime(official_teams_path)
    if (
        _cache_path == str(path)
        and _cache_mtime_ns == stat.st_mtime_ns
        and _cache_overlay_mtime_ns == overlay_mtime
        and _cache_qualification_mtime_ns == qualification_mtime
        and _cache_official_teams_mtime_ns == official_teams_mtime
    ):
        return _cache_doc
    with _cache_lock:
        stat = path.stat()
        overlay_mtime = _mtime(overlay_path)
        qualification_mtime = _mtime(qualification_path)
        official_teams_mtime = _mtime(official_teams_path)
        if (
            _cache_path == str(path)
            and _cache_mtime_ns == stat.st_mtime_ns
            and _cache_overlay_mtime_ns == overlay_mtime
            and _cache_qualification_mtime_ns == qualification_mtime
            and _cache_official_teams_mtime_ns == official_teams_mtime
        ):
            return _cache_doc
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="全员计分数据读取失败") from exc
        if not isinstance(doc, dict):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="全员计分数据格式无效")
        if overlay_path.exists():
            try:
                overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                overlay = {}
            overlay_cells = overlay.get("cells") if isinstance(overlay.get("cells"), list) else []
            overlay_date = str(overlay.get("date") or "")
            overlay_season = str(overlay.get("season") or "")
            if overlay_cells and overlay_date:
                doc = dict(doc)
                doc["cells"] = [
                    cell
                    for cell in (doc.get("cells") or [])
                    if not (
                        str(cell.get("date") or "") == overlay_date
                        and (not overlay_season or str(cell.get("season") or "") == overlay_season)
                    )
                ] + overlay_cells
                if str(overlay.get("generated_at") or "") > str(doc.get("generated_at") or ""):
                    doc["generated_at"] = str(overlay.get("generated_at"))
        doc["qualification"] = _load_json_if_exists(qualification_path)
        doc["official_teams"] = _load_json_if_exists(official_teams_path)
        _cache_path = str(path)
        _cache_mtime_ns = stat.st_mtime_ns
        _cache_overlay_mtime_ns = overlay_mtime
        _cache_qualification_mtime_ns = qualification_mtime
        _cache_official_teams_mtime_ns = official_teams_mtime
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


def _member_index(board: dict[str, Any], season: str = "") -> dict[str, dict[str, Any]]:
    """Merge board metadata with Pocket48 official teams and stage qualification.

    ``board["official_teams"]`` and ``board["qualification"]`` are loaded by
    ``_load_board`` from files in the same directory as ``score_board.json``.
    Tests may inject the same keys directly into a board fixture. Qualification
    is only applied to its declared season, so the summer view never shows the
    winter red-blue stage badge.
    """
    qualification = board.get("qualification") if isinstance(board.get("qualification"), dict) else {}
    official_teams = board.get("official_teams") if isinstance(board.get("official_teams"), dict) else {}
    qualification_members = qualification.get("members") if isinstance(qualification.get("members"), dict) else {}
    qualified_ids = {str(value) for value in qualification.get("qualified_ids") or []}
    participant_ids = {str(value) for value in qualification.get("participant_ids") or []}
    team_members = official_teams.get("members") if isinstance(official_teams.get("members"), dict) else {}
    qualification_season = str(qualification.get("season") or "")
    qualification_available = bool(qualified_ids or participant_ids) and (
        not qualification_season or not season or qualification_season == season
    )
    index: dict[str, dict[str, Any]] = {}
    for item in board.get("members") or []:
        if not isinstance(item, dict) or not item.get("member_id"):
            continue
        member_id = str(item["member_id"])
        meta = dict(item)
        official = team_members.get(member_id)
        if isinstance(official, dict):
            if official.get("group"):
                meta["group"] = str(official["group"])
            if official.get("team"):
                meta["team"] = str(official["team"])
            if official.get("team_label"):
                meta["team_label"] = str(official["team_label"])
            meta["official_team"] = True
        if qualification_available:
            if member_id in qualified_ids:
                meta["qualification"] = "qualified"
            elif member_id in participant_ids:
                meta["qualification"] = "not_qualified"
            else:
                meta["qualification"] = "not_participant"
            meta["qualified"] = meta["qualification"] == "qualified"
            q_member = qualification_members.get(member_id) if isinstance(qualification_members, dict) else {}
            if isinstance(q_member, dict):
                meta["qualification_song"] = str(q_member.get("song") or "")
                meta["qualification_gift"] = str(q_member.get("gift_name") or "")
        else:
            meta["qualification"] = ""
            meta["qualified"] = False
        index[member_id] = meta
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
    qualification: str = "all",
) -> list[dict[str, Any]]:
    group = group.strip()
    team = team.strip()
    member = member.strip().lower()
    gift_name = gift_name.strip()
    members = _member_index(board, season)
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
        if qualification != "all" and str(meta.get("qualification") or "") != qualification:
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
    *,
    season: str = "",
    seed_member_ids: set[str] | None = None,
) -> dict[str, Any]:
    members = _member_index(board, season)
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
                "qualification": str(meta.get("qualification") or ""),
                "qualified": bool(meta.get("qualified")),
                "qualification_song": str(meta.get("qualification_song") or ""),
                "qualification_gift": str(meta.get("qualification_gift") or ""),
                "total_score": 0.0,
                "room_score": 0.0,
                "live_score": 0.0,
                "gnz_score": 0.0,
                "third_party_score": 0.0,
                "total_count": 0,
                "records": 0,
                "gifts": {},
                "first_event_date": "",
                "latest_event_date": "",
            },
        )
        row["total_score"] += score
        if source == "room":
            row["room_score"] += score
        elif source == "live":
            row["live_score"] += score
        elif source in {"gnz", "xox", "third_party"}:
            row["third_party_score"] += score
            if source == "gnz":
                row["gnz_score"] += score
        row["total_count"] += count
        row["records"] += records
        day = str(cell.get("date") or "")
        if day:
            row["first_event_date"] = min(filter(None, [row["first_event_date"], day]))
            row["latest_event_date"] = max(filter(None, [row["latest_event_date"], day]))
        gift_key = gift_id or gift_name
        gift = row["gifts"].setdefault(
            gift_key,
            {"gift_id": gift_id, "gift_name": gift_name, "score": 0.0, "count": 0, "records": 0, "gnz_score": 0.0, "third_party_score": 0.0, "provenance": set()},
        )
        gift["score"] += score
        gift["count"] += count
        gift["records"] += records
        if source in {"gnz", "xox", "third_party"}:
            gift["third_party_score"] += score
            if source == "gnz":
                gift["gnz_score"] += score
            if cell.get("provenance"):
                gift["provenance"].add(str(cell.get("provenance")))

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

    for member_id in seed_member_ids or set():
        if member_id in by_member:
            continue
        meta = members.get(member_id, {})
        if not meta:
            continue
        by_member[member_id] = {
            "member_id": member_id,
            "member_name": str(meta.get("member_name") or member_id),
            "group": str(meta.get("group") or ""),
            "team": str(meta.get("team") or ""),
            "team_label": str(meta.get("team_label") or meta.get("team") or "未分组"),
            "period_name": str(meta.get("period_name") or ""),
            "status": str(meta.get("status") or ""),
            "qualification": str(meta.get("qualification") or ""),
            "qualified": bool(meta.get("qualified")),
            "qualification_song": str(meta.get("qualification_song") or ""),
            "qualification_gift": str(meta.get("qualification_gift") or ""),
            "total_score": 0.0,
            "room_score": 0.0,
            "live_score": 0.0,
            "gnz_score": 0.0,
            "third_party_score": 0.0,
            "total_count": 0,
            "records": 0,
            "gifts": {},
            "first_event_date": "",
            "latest_event_date": "",
        }

    member_rows: list[dict[str, Any]] = []
    for row in by_member.values():
        gifts = sorted(row["gifts"].values(), key=lambda item: (-float(item["score"]), str(item["gift_name"])))
        for gift in gifts:
            gift["provenance"] = sorted(gift.get("provenance") or [])
        row["gifts"] = gifts
        row["total_score"] = round(float(row["total_score"]), 6)
        row["room_score"] = round(float(row["room_score"]), 6)
        row["live_score"] = round(float(row["live_score"]), 6)
        row["gnz_score"] = round(float(row["gnz_score"]), 6)
        row["third_party_score"] = round(float(row["third_party_score"]), 6)
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
    gnz_score = sum(float(row["gnz_score"]) for row in member_rows)
    third_party_score = sum(float(row["third_party_score"]) for row in member_rows)
    total_score = sum(float(row["total_score"]) for row in member_rows)
    return {
        "summary": {
            "total_score": round(total_score, 6),
            "room_score": round(room_score, 6),
            "live_score": round(live_score, 6),
            "gnz_score": round(gnz_score, 6),
            "third_party_score": round(third_party_score, 6),
            "total_count": sum(int(row["total_count"]) for row in member_rows),
            "records": sum(int(row["records"]) for row in member_rows),
            "members": len(member_rows),
            "qualified_members": sum(1 for row in member_rows if row["qualification"] == "qualified"),
            "participant_members": sum(1 for row in member_rows if row["qualification"] in {"qualified", "not_qualified"}),
            "not_qualified_members": sum(1 for row in member_rows if row["qualification"] == "not_qualified"),
            "not_participant_members": sum(1 for row in member_rows if row["qualification"] == "not_participant"),
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
    members = _member_index(board, season)
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
    qualification_counts = {"qualified": 0, "not_qualified": 0, "not_participant": 0, "unknown": 0}
    qualification_doc = board.get("qualification") if isinstance(board.get("qualification"), dict) else {}
    qualification_season = str(qualification_doc.get("season") or "")
    qualification_for_season = not qualification_season or qualification_season == season
    qualified_ids = {str(value) for value in qualification_doc.get("qualified_ids") or []}
    participant_ids = {str(value) for value in qualification_doc.get("participant_ids") or []}
    if qualification_for_season and (qualified_ids or participant_ids):
        qualification_counts["qualified"] = len(qualified_ids)
        qualification_counts["not_qualified"] = len(participant_ids - qualified_ids)
        qualification_counts["not_participant"] = len(member_ids - participant_ids)
    else:
        for member_id in member_ids:
            status = str((members.get(member_id) or {}).get("qualification") or "")
            if status in qualification_counts:
                qualification_counts[status] += 1
            else:
                qualification_counts["unknown"] += 1
    return {
        "groups": sorted(groups),
        "teams": sorted(teams.values(), key=lambda item: (item["group"], item["team"])),
        "gifts": gifts,
        "members": len(member_ids),
        "qualification_counts": qualification_counts,
        "qualification_available": bool(
            (board.get("qualification") or {}).get("qualified_ids")
            or (board.get("qualification") or {}).get("participant_ids")
        ),
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
    return {
        "generated_at": str(board.get("generated_at", "")),
        "timezone": str(board.get("timezone", "Asia/Shanghai")),
        "season": key,
        "seasons": board.get("seasons", {}),
        "latest_season": board.get("latest_season", ""),
        "gift_authority": board.get("gift_authority", []),
        "coverage_notes": board.get("coverage_notes") or {},
        "coverage_summary": str(board.get("coverage_summary", "")),
        "provenance_summary": board.get("provenance_summary") or {},
        "qualification": board.get("qualification") or {},
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
    qualification: str = Query("all"),
    sort: str = Query("score_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=2000),
    _=Depends(verify_score_gifts_password),
):
    response.headers["Cache-Control"] = "no-store"
    source = source.strip().lower()
    sort = sort.strip().lower()
    qualification = qualification.strip().lower()
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的数据来源")
    if sort not in VALID_SORTS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的排序方式")
    if qualification not in VALID_QUALIFICATIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的红蓝晋级筛选")
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
        qualification=qualification,
    )
    seed_ids: set[str] = set()
    qualification_doc = board.get("qualification") if isinstance(board.get("qualification"), dict) else {}
    qualification_season = str(qualification_doc.get("season") or "")
    qualification_for_season = not qualification_season or qualification_season == key
    if not (gift_name or date_from or date_to or source != "all") and qualification_for_season:
        qualified_ids = {str(value) for value in qualification_doc.get("qualified_ids") or []}
        participant_ids = {str(value) for value in qualification_doc.get("participant_ids") or []}
        if qualification == "qualified":
            seed_ids = qualified_ids
        elif qualification == "not_qualified":
            seed_ids = participant_ids - qualified_ids
        elif qualification == "all":
            seed_ids = participant_ids
        if seed_ids and (group or team or member):
            members_index = _member_index(board, key)
            member_query = member.strip().lower()
            filtered: set[str] = set()
            for member_id in seed_ids:
                meta = members_index.get(member_id) or {}
                if group and str(meta.get("group") or "") != group.strip():
                    continue
                if team and str(meta.get("team") or "") != team.strip():
                    continue
                if member_query:
                    haystack = f"{meta.get('member_name') or ''} {member_id}".lower()
                    if member_query not in haystack:
                        continue
                filtered.add(member_id)
            seed_ids = filtered
    aggregated = _aggregate(board, cells, season=key, seed_member_ids=seed_ids)
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
    return {
        "generated_at": str(board.get("generated_at", "")),
        "timezone": str(board.get("timezone", "Asia/Shanghai")),
        "season": key,
        "seasons": board.get("seasons", {}),
        "latest_season": board.get("latest_season", ""),
        "gift_authority": board.get("gift_authority", []),
        "coverage_notes": board.get("coverage_notes") or {},
        "coverage_summary": str(board.get("coverage_summary", "")),
        "provenance_summary": board.get("provenance_summary") or {},
        "qualification": board.get("qualification") or {},
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

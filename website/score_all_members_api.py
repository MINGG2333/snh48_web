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
VALID_SORTS = {"score_desc", "estimate_desc", "name_asc", "team_asc"}
VALID_QUALIFICATIONS = {"all", "qualified", "not_qualified", "not_participant"}
QUALIFICATION_FILENAME = "redblue_stage1_qualification.json"
AFFILIATION_FILENAME = "redblue_affiliation.json"
FAN_SCORES_FILENAME = "member_fan_scores.json"
OFFICIAL_TEAMS_FILENAME = "official_member_teams.json"
# 红蓝歌会第一阶段计分截止日（含当天）。暗票只用这天的明票反推一次，之后固定。
STAGE1_SCORE_CUTOFF_DEFAULT = "2026-11-15"

_cache_lock = threading.Lock()
_cache_path = ""
_cache_mtime_ns = -1
_cache_overlay_mtime_ns = -1
_cache_qualification_mtime_ns = -1
_cache_affiliation_mtime_ns = -1
_cache_fan_scores_mtime_ns = -1
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
    global _cache_qualification_mtime_ns, _cache_affiliation_mtime_ns
    global _cache_fan_scores_mtime_ns, _cache_official_teams_mtime_ns, _cache_doc
    path = Path(cfg.SCORE_ALL_MEMBERS_DATA_PATH)
    overlay_path = path.parent / "realtime_cells.json"
    qualification_path = path.parent / QUALIFICATION_FILENAME
    affiliation_path = path.parent / AFFILIATION_FILENAME
    fan_scores_path = path.parent / FAN_SCORES_FILENAME
    official_teams_path = path.parent / OFFICIAL_TEAMS_FILENAME
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="全员计分数据未生成")

    def _mtime(candidate: Path) -> int:
        return candidate.stat().st_mtime_ns if candidate.exists() else 0

    stat = path.stat()
    overlay_mtime = _mtime(overlay_path)
    qualification_mtime = _mtime(qualification_path)
    affiliation_mtime = _mtime(affiliation_path)
    fan_scores_mtime = _mtime(fan_scores_path)
    official_teams_mtime = _mtime(official_teams_path)
    if (
        _cache_path == str(path)
        and _cache_mtime_ns == stat.st_mtime_ns
        and _cache_overlay_mtime_ns == overlay_mtime
        and _cache_qualification_mtime_ns == qualification_mtime
        and _cache_affiliation_mtime_ns == affiliation_mtime
        and _cache_fan_scores_mtime_ns == fan_scores_mtime
        and _cache_official_teams_mtime_ns == official_teams_mtime
    ):
        return _cache_doc
    with _cache_lock:
        stat = path.stat()
        overlay_mtime = _mtime(overlay_path)
        qualification_mtime = _mtime(qualification_path)
        affiliation_mtime = _mtime(affiliation_path)
        fan_scores_mtime = _mtime(fan_scores_path)
        official_teams_mtime = _mtime(official_teams_path)
        if (
            _cache_path == str(path)
            and _cache_mtime_ns == stat.st_mtime_ns
            and _cache_overlay_mtime_ns == overlay_mtime
            and _cache_qualification_mtime_ns == qualification_mtime
            and _cache_affiliation_mtime_ns == affiliation_mtime
            and _cache_fan_scores_mtime_ns == fan_scores_mtime
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
        doc["affiliation"] = _load_json_if_exists(affiliation_path)
        doc["fan_scores"] = _load_json_if_exists(fan_scores_path)
        doc["official_teams"] = _load_json_if_exists(official_teams_path)
        _cache_path = str(path)
        _cache_mtime_ns = stat.st_mtime_ns
        _cache_overlay_mtime_ns = overlay_mtime
        _cache_qualification_mtime_ns = qualification_mtime
        _cache_affiliation_mtime_ns = affiliation_mtime
        _cache_fan_scores_mtime_ns = fan_scores_mtime
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


def _fan_payload(board: dict[str, Any], season: str, member_id: str) -> dict[str, Any]:
    doc = board.get("fan_scores") if isinstance(board.get("fan_scores"), dict) else {}
    season_doc = (doc.get("seasons") or {}).get(season) if isinstance(doc.get("seasons"), dict) else {}
    member = (season_doc or {}).get("members", {}).get(member_id) if isinstance(season_doc, dict) else None
    payload: dict[str, Any] = {
        "generated_at": str(doc.get("generated_at") or ""),
        "season": season,
        "fan_limit": int(doc.get("fan_limit") or 0),
        "member_id": member_id,
        "member_name": "",
        "fan_count": 0,
        "total_score": 0.0,
        "fans": [],
        "truncated": False,
    }
    if isinstance(member, dict):
        payload.update(
            {
                "member_name": str(member.get("member_name") or ""),
                "fan_count": int(member.get("fan_count") or 0),
                "total_score": round(float(member.get("total_score") or 0), 6),
                "fans": member.get("fans") if isinstance(member.get("fans"), list) else [],
            }
        )
    payload["truncated"] = payload["fan_count"] > len(payload["fans"])
    return payload


def _member_index(board: dict[str, Any], season: str = "") -> dict[str, dict[str, Any]]:
    """Merge board metadata with Pocket48 official teams and stage qualification.

    ``board["official_teams"]`` and ``board["qualification"]`` are loaded by
    ``_load_board`` from files in the same directory as ``score_board.json``.
    Tests may inject the same keys directly into a board fixture. Qualification
    is only applied to its declared season, so the summer view never shows the
    winter red-blue stage badge.
    """
    qualification = board.get("qualification") if isinstance(board.get("qualification"), dict) else {}
    affiliation = board.get("affiliation") if isinstance(board.get("affiliation"), dict) else {}
    official_teams = board.get("official_teams") if isinstance(board.get("official_teams"), dict) else {}
    qualification_members = qualification.get("members") if isinstance(qualification.get("members"), dict) else {}
    affiliation_members = affiliation.get("members") if isinstance(affiliation.get("members"), dict) else {}
    qualified_ids = {str(value) for value in qualification.get("qualified_ids") or []}
    participant_ids = {str(value) for value in qualification.get("participant_ids") or []}
    team_members = official_teams.get("members") if isinstance(official_teams.get("members"), dict) else {}
    qualification_season = str(qualification.get("season") or "")
    affiliation_season = str(affiliation.get("season") or "")
    qualification_available = bool(qualified_ids or participant_ids) and (
        not qualification_season or not season or qualification_season == season
    )
    affiliation_available = bool(affiliation_members) and (
        not affiliation_season or not season or affiliation_season == season
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
            if meta.get("team") == "IDFT":
                meta["team_label"] = "IDFT"
            meta["official_team"] = True
        elif meta.get("team") == "IDFT":
            meta["team_label"] = "IDFT"
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
        # 期数以官方参赛名单（pname）为准，覆盖 members_id.csv 的历史快照。
        # 该字段与赛季无关，所以不放在 qualification_available 分支里。
        q_member_all = qualification_members.get(member_id) if isinstance(qualification_members, dict) else None
        if isinstance(q_member_all, dict):
            official_period = str(q_member_all.get("official_event_period") or "").strip()
            if official_period:
                meta["period_name"] = official_period
        meta["trainee"] = False
        meta["affiliation_team"] = ""
        meta["affiliation_label"] = ""
        meta["affiliation_status"] = ""
        meta["participation_team"] = ""
        meta["participation_team_label"] = ""
        meta["unit"] = ""
        meta["unit_label"] = ""
        meta["unit_rank"] = 0
        meta["official_qualified"] = False
        aff_member = affiliation_members.get(member_id) if affiliation_available else None
        if isinstance(aff_member, dict):
            meta["trainee"] = bool(aff_member.get("trainee"))
            meta["affiliation_team"] = str(aff_member.get("affiliation_team") or "")
            meta["affiliation_label"] = str(aff_member.get("affiliation_label") or "")
            meta["participation_team"] = str(aff_member.get("participation_team") or "")
            meta["participation_team_label"] = str(aff_member.get("participation_team_label") or "")
            meta["unit"] = str(aff_member.get("unit") or "")
            meta["unit_label"] = str(aff_member.get("unit_label") or "")
            try:
                meta["unit_rank"] = int(aff_member.get("unit_rank") or 0)
            except (TypeError, ValueError):
                meta["unit_rank"] = 0
            meta["official_qualified"] = bool(aff_member.get("official_qualified"))
            if meta["affiliation_team"]:
                meta["affiliation_status"] = "official"
            elif meta["trainee"]:
                meta["affiliation_status"] = "unlisted"
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
    unit: str = "",
    participation_team: str = "",
) -> list[dict[str, Any]]:
    group = group.strip()
    team = team.strip()
    if "|" in team:
        team_group, _, team_name = team.partition("|")
        if group and group != team_group:
            return []
        group = team_group
        team = team_name
    participation_team = participation_team.strip()
    unit = unit.strip()
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
        if unit and str(meta.get("unit") or "") != unit:
            continue
        if participation_team:
            p_group, _, p_team = participation_team.partition("|")
            if str(meta.get("group") or "") != p_group or str(meta.get("participation_team") or "") != p_team:
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
    dark_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """按计分 cell 聚合成员/礼物/队伍/日期分布。

    ``dark_scores`` 为「成员 → 固定暗票」，只用于给队伍分布补充
    ``estimated_score``（页面的「总分（估计）」口径）。估计分完全跟随筛选：
    该行当前筛选内的明票合计 + 固定暗票；不传时退化为当前明票合计。
    """
    members = _member_index(board, season)
    by_member: dict[str, dict[str, Any]] = {}
    gift_distribution: dict[tuple[str, str], dict[str, Any]] = {}
    team_distribution: dict[tuple[str, str], dict[str, Any]] = {}
    participation_team_distribution: dict[tuple[str, str], dict[str, Any]] = {}
    daily_distribution: dict[str, dict[str, Any]] = {}

    # Some older room events carry giftName but no giftId. Normalize them to
    # the known gift id so the page shows one "琴音生花" row instead of two.
    gift_name_to_id: dict[str, str] = {}
    for entry in board.get("gift_authority") or []:
        if not isinstance(entry, dict):
            continue
        known_id = str(entry.get("gift_id") or "").strip()
        known_name = str(entry.get("gift_name") or "").strip()
        if known_id and known_name:
            gift_name_to_id.setdefault(known_name, known_id)
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        known_id = str(cell.get("gift_id") or "").strip()
        known_name = str(cell.get("gift_name") or "").strip()
        if known_id and known_name:
            gift_name_to_id.setdefault(known_name, known_id)

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
        gift_id = str(cell.get("gift_id") or "").strip()
        gift_name = str(cell.get("gift_name") or "").strip()
        if not gift_id and gift_name:
            gift_id = gift_name_to_id.get(gift_name, "")

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
                "trainee": bool(meta.get("trainee")),
                "affiliation_team": str(meta.get("affiliation_team") or ""),
                "affiliation_label": str(meta.get("affiliation_label") or ""),
                "affiliation_status": str(meta.get("affiliation_status") or ""),
                "unit": str(meta.get("unit") or ""),
                "unit_label": str(meta.get("unit_label") or ""),
                "participation_team": str(meta.get("participation_team") or ""),
                "participation_team_label": str(meta.get("participation_team_label") or ""),
                "unit_rank": int(meta.get("unit_rank") or 0),
                "official_qualified": bool(meta.get("official_qualified")),
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

        # 参赛队伍：挂靠预备生并入其挂靠队（official 队伍不变），未参与本次
        # 活动的成员单独归为「未参赛」，避免挂靠视角把非参赛成员混进某队。
        p_team = str(meta.get("participation_team") or "")
        p_label = str(meta.get("participation_team_label") or "")
        if not p_label:
            p_label = "未参赛" if not p_team else p_team
        p_key = (group, p_team or "未参赛")
        participation_row = participation_team_distribution.setdefault(
            p_key,
            {
                "group": group,
                "participation_team": p_team,
                "participation_team_label": p_label,
                "score": 0.0,
                "count": 0,
                "members": set(),
            },
        )
        participation_row["score"] += score
        participation_row["count"] += count
        participation_row["members"].add(member_id)

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
            "trainee": bool(meta.get("trainee")),
            "affiliation_team": str(meta.get("affiliation_team") or ""),
            "affiliation_label": str(meta.get("affiliation_label") or ""),
            "affiliation_status": str(meta.get("affiliation_status") or ""),
            "unit": str(meta.get("unit") or ""),
            "unit_label": str(meta.get("unit_label") or ""),
            "participation_team": str(meta.get("participation_team") or ""),
            "participation_team_label": str(meta.get("participation_team_label") or ""),
            "unit_rank": int(meta.get("unit_rank") or 0),
            "official_qualified": bool(meta.get("official_qualified")),
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

    # 队伍维度同时给出明票（当前筛选内 cell 合计）与总分（估计）：
    # 后者是该行成员各自的完整赛季估计分之和，成员集合仍由当前筛选决定。
    member_estimated: dict[str, float] = {}
    dark_scores = dark_scores or {}
    for row in member_rows:
        member_id = str(row["member_id"])
        member_estimated[member_id] = float(row["total_score"]) + float(
            dark_scores.get(member_id) or 0.0
        )

    def _team_rows(distribution: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in distribution.values():
            member_ids = row["members"]
            item = {key: value for key, value in row.items() if key != "members"}
            item["members"] = len(member_ids)
            item["score"] = round(float(item["score"]), 6)
            item["estimated_score"] = round(
                sum(member_estimated.get(member_id, 0.0) for member_id in member_ids), 6
            )
            rows.append(item)
        rows.sort(
            key=lambda item: (
                -float(item["score"]),
                str(item.get("group") or ""),
                str(item.get("team_label") or item.get("participation_team_label") or ""),
            )
        )
        return rows

    team_rows = _team_rows(team_distribution)
    participation_team_rows = _team_rows(participation_team_distribution)

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
        "participation_team_distribution": participation_team_rows,
        "daily_distribution": daily_rows,
    }


def _stage1_score_cutoff(board: dict[str, Any]) -> str:
    """第一阶段计分截止日（含当天）。

    暗票只代表第一阶段结束时的不可采集计分；用这一天的明票反推一次后固定，
    后续新增的明票只抬高「总分（估计）」，不再改变暗票。挂靠文件可提供
    ``official_result.score_cutoff`` 覆盖默认值。
    """
    affiliation = board.get("affiliation") if isinstance(board.get("affiliation"), dict) else {}
    official = affiliation.get("official_result") if isinstance(affiliation.get("official_result"), dict) else {}
    for field in ("score_cutoff", "stage1_score_cutoff"):
        value = str(official.get(field) or "").strip()
        if DATE_RE.match(value[:10]):
            return value[:10]
    return STAGE1_SCORE_CUTOFF_DEFAULT


def _estimate_context(
    board: dict[str, Any], season: str
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """返回 (当前完整赛季明票合计, 每人固定暗票与动态估计)。

    * 明票合计 ``visible_totals``：赛季全部计分 cell（随采集持续增长）；
    * 暗票：只用第一阶段截止日（含当天）的明票反推并固定，之后不再变化；
    * 总分（估计）= 当前完整赛季明票 + 固定暗票（因此是动态的）。

    挂靠数据缺失或赛季不符时都为空。
    """
    affiliation = board.get("affiliation") if isinstance(board.get("affiliation"), dict) else {}
    affiliation_season = str(affiliation.get("season") or "")
    if not affiliation.get("members") or (
        affiliation_season and season and affiliation_season != season
    ):
        return {}, {}
    visible_totals = _season_visible_totals(board, season)
    cutoff = _stage1_score_cutoff(board)
    stage1_totals = (
        _season_visible_totals(board, season, date_to=cutoff)
        if cutoff
        else visible_totals
    )
    estimates = _unit_rank_estimates(board, season, stage1_totals)
    frozen_at = cutoff or "赛季全部"
    for member_id, item in estimates.items():
        visible = float(visible_totals.get(member_id) or 0.0)
        dark = float(item.get("dark_min_score") or 0.0)
        item["stage1_visible_score"] = round(float(item.get("visible_total_score") or 0.0), 6)
        item["visible_total_score"] = round(visible, 6)
        item["estimated_total_score"] = round(visible + dark, 6)
        item["dark_frozen_at"] = frozen_at
    return visible_totals, estimates


def _dark_scores(estimates: dict[str, dict[str, Any]]) -> dict[str, float]:
    """从反推结果中取出「成员 → 固定暗票」，供筛选后的估计分使用。"""
    return {
        str(member_id): float(item.get("dark_min_score") or 0.0)
        for member_id, item in estimates.items()
    }


def _season_visible_totals(
    board: dict[str, Any], season: str, *, date_to: str = ""
) -> dict[str, float]:
    """按成员汇总计分 cell（明票）。

    ``date_to`` 非空时只统计该日期（含）之前的 cell，用于还原第一阶段结束时的
    明票；不带日期信息的 cell 视为包含在内。
    """
    totals: dict[str, float] = {}
    for cell in board.get("cells") or []:
        if not isinstance(cell, dict) or cell.get("season") != season:
            continue
        day = str(cell.get("date") or "")
        if date_to and day and day > date_to:
            continue
        member_id = str(cell.get("member_id") or "")
        if not member_id:
            continue
        totals[member_id] = totals.get(member_id, 0.0) + float(cell.get("score") or 0)
    return totals


def _unit_rank_estimates(
    board: dict[str, Any],
    season: str,
    visible_totals: dict[str, float],
) -> dict[str, dict[str, Any]]:
    """由官方队内排名反推每人「最少暗票」与「总分（估计）」。

    真实分 s = 明票 g + 暗票 d。官方 64 人名单只给出每个晋级单元前 8 名的
    队内顺序（第一阶段计分由高到低），因此只有前 8 名有硬约束：

    * s_i >= s_{i+1}（官方顺序，同分不排除，按 >= 处理）；
    * 晋级末位 s_8 还要不低于该单元所有未晋级参赛者的真实分，而后者又至少等于
      各自可见明票，所以 s_8 >= 未晋级成员的最高明票。

    从末位往上扫，取 s_i = max(g_i, s_{i+1})，即可得到每个人在满足官方顺序
    前提下的最小暗票（逐分量最小解）。这里的 ``visible_totals`` 是**第一阶段
    截止日**的明票；调用方 ``_estimate_context`` 会把结果固定为暗票，再用当前
    明票重算总分（估计）。未晋级成员没有可用的排名约束，最少暗票记为 0。
    """
    affiliation = board.get("affiliation") if isinstance(board.get("affiliation"), dict) else {}
    affiliation_season = str(affiliation.get("season") or "")
    if affiliation_season and season and affiliation_season != season:
        return {}
    members = affiliation.get("members") if isinstance(affiliation.get("members"), dict) else {}
    if not members:
        return {}
    unit_labels: dict[str, str] = {}
    for unit in affiliation.get("units") or []:
        if isinstance(unit, dict) and unit.get("key"):
            unit_labels[str(unit["key"])] = str(unit.get("label") or unit["key"])
    by_unit: dict[str, list[tuple[int, str]]] = {}
    for member_id, member in members.items():
        if not isinstance(member, dict):
            continue
        unit = str(member.get("unit") or "")
        if not unit:
            continue
        try:
            rank = int(member.get("unit_rank") or 0)
        except (TypeError, ValueError):
            rank = 0
        by_unit.setdefault(unit, []).append((rank, str(member_id)))

    estimates: dict[str, dict[str, Any]] = {}
    for unit, entries in by_unit.items():
        ranked = sorted(
            ((rank, member_id) for rank, member_id in entries if rank > 0),
            key=lambda item: item[0],
        )
        if not ranked:
            continue
        unranked = [member_id for rank, member_id in entries if rank <= 0]
        # 官方名单只覆盖晋级的前 8 名；同单元未晋级者的可见明票同样是晋级成员的
        # 下界（他们一定排在晋级末位之后），用最高者收紧末位约束。
        unqualified_floor = max(
            (float(visible_totals.get(member_id) or 0.0) for member_id in unranked),
            default=0.0,
        )
        boundary = unqualified_floor
        for rank, member_id in reversed(ranked):
            visible = float(visible_totals.get(member_id) or 0.0)
            estimated = max(visible, boundary)
            estimates[member_id] = {
                "unit": unit,
                "unit_label": unit_labels.get(unit, unit),
                "unit_rank": rank,
                "ranked_in_unit": True,
                "visible_total_score": round(visible, 6),
                "dark_min_score": round(estimated - visible, 6),
                "estimated_total_score": round(estimated, 6),
                "unqualified_floor": round(unqualified_floor, 6),
            }
            boundary = estimated
        for member_id in unranked:
            visible = float(visible_totals.get(member_id) or 0.0)
            estimates[member_id] = {
                "unit": unit,
                "unit_label": unit_labels.get(unit, unit),
                "unit_rank": 0,
                "ranked_in_unit": False,
                "visible_total_score": round(visible, 6),
                "dark_min_score": 0.0,
                "estimated_total_score": round(visible, 6),
                "unqualified_floor": round(unqualified_floor, 6),
            }
    return estimates


def _attach_dark_estimates(
    board: dict[str, Any],
    rows: list[dict[str, Any]],
    season: str,
    *,
    visible_totals: dict[str, float] | None = None,
    estimates: dict[str, dict[str, Any]] | None = None,
) -> None:
    """给成员行补上明票/最少暗票/总分（估计）。

    明票是该成员当前筛选内的合计；暗票按第一阶段截止日的明票反推后固定。
    总分（估计）**完全跟随筛选**：该行当前明票 + 固定暗票（不再用完整赛季
    明票补齐），因此日期/礼物/来源/成员筛选都会同步改变估计分。
    """
    if visible_totals is None or estimates is None:
        visible_totals, estimates = _estimate_context(board, season)
    for row in rows:
        member_id = str(row.get("member_id") or "")
        estimate = estimates.get(member_id)
        visible_total = float(visible_totals.get(member_id, row.get("total_score") or 0.0))
        row["visible_total_score"] = round(visible_total, 6)
        filtered_total = float(row.get("total_score") or 0.0)
        if estimate:
            row["ranked_in_unit"] = bool(estimate.get("ranked_in_unit"))
            row["dark_min_score"] = float(estimate["dark_min_score"])
            row["estimated_total_score"] = round(
                filtered_total + float(estimate["dark_min_score"]), 6
            )
        else:
            row["ranked_in_unit"] = False
            row["dark_min_score"] = None
            row["estimated_total_score"] = round(filtered_total, 6)


def _facets(board: dict[str, Any], season: str) -> dict[str, Any]:
    members = _member_index(board, season)
    groups: set[str] = set()
    teams: dict[tuple[str, str], dict[str, str]] = {}
    member_ids: set[str] = set()
    gift_keys: set[str] = set()
    gift_name_to_id: dict[str, str] = {}
    for entry in board.get("gift_authority") or []:
        if not isinstance(entry, dict):
            continue
        known_id = str(entry.get("gift_id") or "").strip()
        known_name = str(entry.get("gift_name") or "").strip()
        if known_id and known_name:
            gift_name_to_id.setdefault(known_name, known_id)
    for cell in board.get("cells") or []:
        if not isinstance(cell, dict) or cell.get("season") != season:
            continue
        known_id = str(cell.get("gift_id") or "").strip()
        known_name = str(cell.get("gift_name") or "").strip()
        if known_id and known_name:
            gift_name_to_id.setdefault(known_name, known_id)
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
                "key": f"{group}|{team}",
                "group": group,
                "team": team,
                "team_label": str(meta.get("team_label") or team),
            }
        gift_id = str(cell.get("gift_id") or "").strip()
        gift_name = str(cell.get("gift_name") or "").strip()
        if not gift_id and gift_name:
            gift_id = gift_name_to_id.get(gift_name, "")
        gift_keys.add(gift_id or gift_name)
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
    affiliation_doc = board.get("affiliation") if isinstance(board.get("affiliation"), dict) else {}
    affiliation_season = str(affiliation_doc.get("season") or "")
    affiliation_for_season = bool(affiliation_doc) and (
        not affiliation_season or affiliation_season == season
    )
    participation_teams: dict[str, dict[str, str]] = {}
    if affiliation_for_season:
        for aff_id, aff in (affiliation_doc.get("members") or {}).items():
            if not isinstance(aff, dict):
                continue
            p_team = str(aff.get("participation_team") or "")
            p_group = str(aff.get("official_group") or (members.get(str(aff_id)) or {}).get("group") or "")
            if not p_team or not p_group:
                continue
            key = f"{p_group}|{p_team}"
            participation_teams.setdefault(
                key,
                {
                    "key": key,
                    "group": p_group,
                    "team": p_team,
                    "team_label": str(aff.get("participation_team_label") or p_team),
                },
            )
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
        "participation_teams": sorted(
            participation_teams.values(), key=lambda item: (item["group"], item["team"])
        ),
        "gifts": gifts,
        "members": len(member_ids),
        "qualification_counts": qualification_counts,
        "qualification_available": bool(
            (board.get("qualification") or {}).get("qualified_ids")
            or (board.get("qualification") or {}).get("participant_ids")
        ),
        "units": [
            {
                "key": str(unit.get("key")),
                "label": str(unit.get("label") or unit.get("key")),
                "group": str(unit.get("group") or ""),
                "slots": int(unit.get("slots") or 0),
                "qualified": int(unit.get("qualified") or 0),
                "participants": int(unit.get("participants") or 0),
                "qualified_trainees": int(unit.get("qualified_trainees") or 0),
                "official_order": [
                    str(name) for name in (unit.get("official_order") or []) if str(name)
                ],
            }
            for unit in (affiliation_doc.get("units") or [])
            if affiliation_for_season and isinstance(unit, dict) and unit.get("key")
        ],
        "affiliation_available": affiliation_for_season,
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
        "affiliation": {
            "generated_at": str((board.get("affiliation") or {}).get("generated_at") or ""),
            "season": str((board.get("affiliation") or {}).get("season") or ""),
            "stage_label": str((board.get("affiliation") or {}).get("stage_label") or ""),
            "source": (board.get("affiliation") or {}).get("source") or {},
            "units": (board.get("affiliation") or {}).get("units") or [],
            "official_result": (board.get("affiliation") or {}).get("official_result") or {},
        },
        "facets": _facets(board, key),
    }


@router.get("/member-fans")
def get_member_fans(
    response: Response,
    season: str = Query(""),
    member_id: str = Query(""),
    _=Depends(verify_score_gifts_password),
):
    response.headers["Cache-Control"] = "no-store"
    member_id = member_id.strip()
    if not member_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="缺少成员 ID")
    board = _load_board()
    key = _season_key(board, season)
    return _fan_payload(board, key, member_id)


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
    unit: str = Query(""),
    participation_team: str = Query(""),
    sort: str = Query("score_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=2000),
    _=Depends(verify_score_gifts_password),
):
    response.headers["Cache-Control"] = "no-store"
    source = source.strip().lower()
    sort = sort.strip().lower()
    qualification = qualification.strip().lower()
    unit = unit.strip()
    participation_team = participation_team.strip()
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
        unit=unit,
        participation_team=participation_team,
    )
    seed_ids: set[str] = set()
    qualification_doc = board.get("qualification") if isinstance(board.get("qualification"), dict) else {}
    qualification_season = str(qualification_doc.get("season") or "")
    qualification_for_season = not qualification_season or qualification_season == key
    if not (gift_name or date_from or date_to or source != "all"):
        members_index = _member_index(board, key)
        qualified_ids = {str(value) for value in qualification_doc.get("qualified_ids") or []}
        participant_ids = {str(value) for value in qualification_doc.get("participant_ids") or []}
        has_scope_filter = bool(group or team or member or unit or participation_team)
        if qualification_for_season and qualification == "qualified":
            seed_ids = qualified_ids
        elif qualification_for_season and qualification == "not_qualified":
            seed_ids = participant_ids - qualified_ids
        elif qualification_for_season and qualification == "not_participant":
            seed_ids = set(members_index) - participant_ids
        elif has_scope_filter:
            # When filtering by group/team/member, include zero-score members too
            # so IDFT and other non-scoring members are visible with their official team.
            seed_ids = set(members_index)
        elif qualification_for_season:
            seed_ids = participant_ids
        if seed_ids and has_scope_filter:
            member_query = member.strip().lower()
            seed_group = group.strip()
            seed_team = team.strip()
            if "|" in seed_team:
                group_from_team, _, team_name = seed_team.partition("|")
                seed_group = seed_group or group_from_team
                if seed_group != group_from_team:
                    seed_ids = set()
                seed_team = team_name
            seed_p_group, _, seed_p_team = participation_team.partition("|")
            filtered: set[str] = set()
            for member_id in seed_ids:
                meta = members_index.get(member_id) or {}
                if seed_group and str(meta.get("group") or "") != seed_group:
                    continue
                if seed_team and str(meta.get("team") or "") != seed_team:
                    continue
                if unit and str(meta.get("unit") or "") != unit:
                    continue
                if participation_team and (
                    str(meta.get("group") or "") != seed_p_group
                    or str(meta.get("participation_team") or "") != seed_p_team
                ):
                    continue
                if member_query:
                    haystack = f"{meta.get('member_name') or ''} {member_id}".lower()
                    if member_query not in haystack:
                        continue
                filtered.add(member_id)
            seed_ids = filtered
    visible_totals, estimates = _estimate_context(board, key)
    aggregated = _aggregate(
        board,
        cells,
        season=key,
        seed_member_ids=seed_ids,
        dark_scores=_dark_scores(estimates),
    )
    rows = aggregated["members"]
    _attach_dark_estimates(
        board, rows, key, visible_totals=visible_totals, estimates=estimates
    )
    if sort == "name_asc":
        rows.sort(key=lambda item: (str(item["group"]), str(item["team"]), str(item["member_name"])))
    elif sort == "team_asc":
        rows.sort(key=lambda item: (str(item["group"]), str(item["team"]), -float(item["total_score"]), str(item["member_name"])))
    elif sort == "estimate_desc":
        # 同一单元内分数相同时按官方队内名次排，避免「第 3 名排在第 4 名之后」。
        rows.sort(
            key=lambda item: (
                -float(item.get("estimated_total_score") or 0),
                str(item.get("unit") or ""),
                int(item.get("unit_rank") or 0) if item.get("unit_rank") else 10**6,
                -float(item["total_score"]),
                str(item["member_name"]),
            )
        )
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
        "affiliation": {
            "generated_at": str((board.get("affiliation") or {}).get("generated_at") or ""),
            "season": str((board.get("affiliation") or {}).get("season") or ""),
            "stage_label": str((board.get("affiliation") or {}).get("stage_label") or ""),
            "source": (board.get("affiliation") or {}).get("source") or {},
            "units": (board.get("affiliation") or {}).get("units") or [],
            "official_result": (board.get("affiliation") or {}).get("official_result") or {},
        },
        "facets": _facets(board, key),
        "summary": aggregated["summary"],
        "members": rows[start:end],
        "gift_distribution": aggregated["gift_distribution"],
        "team_distribution": aggregated["team_distribution"],
        "participation_team_distribution": aggregated["participation_team_distribution"],
        "daily_distribution": aggregated["daily_distribution"],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from website import config as cfg
from website.score_all_members_api import (
    _aggregate,
    _attach_dark_estimates,
    _estimate_context,
    _facets,
    _fan_payload,
    _filter_cells,
    _load_board,
    _merge_estimated_totals,
    _season_key,
    _season_visible_totals,
    _unit_rank_estimates,
)
from website.score_gifts_api import _data_path


BOARD = {
    "version": 1,
    "latest_season": "2026-winter",
    "seasons": {
        "2026-summer": {
            "key": "2026-summer",
            "label": "2026 青春盛典",
            "start_date": "2026-05-30",
            "end_date": "2026-08-08",
        },
        "2026-winter": {
            "key": "2026-winter",
            "label": "2026 红蓝歌会",
            "start_date": "2026-10-24",
            "end_date": "",
        },
    },
    "coverage": {"seasons": {"2026-winter": {"complete": True}}},
    "gift_authority": [
        {
            "gift_id": "g1",
            "gift_name": "弦月回响",
            "unit_score": 1.0,
            "is_score": True,
            "seasons": ["2026-winter"],
        }
    ],
    "members": [
        {"member_id": "1", "member_name": "甲", "group": "SNH48", "team": "HII", "team_label": "HII队"},
        {"member_id": "2", "member_name": "乙", "group": "SNH48", "team": "SII", "team_label": "SII队"},
        {"member_id": "3", "member_name": "丙", "group": "GNZ48", "team": "G", "team_label": "G队"},
    ],
    "cells": [
        {"season": "2026-winter", "date": "2026-10-24", "source": "room", "member_id": "1", "gift_id": "g1", "gift_name": "弦月回响", "count": 5, "score": 5.0, "records": 2},
        {"season": "2026-winter", "date": "2026-10-24", "source": "live", "member_id": "1", "gift_id": "g1", "gift_name": "弦月回响", "count": 2, "score": 2.0, "records": 1},
        {"season": "2026-winter", "date": "2026-10-25", "source": "room", "member_id": "2", "gift_id": "g1", "gift_name": "弦月回响", "count": 3, "score": 3.0, "records": 1},
        {"season": "2026-summer", "date": "2026-08-01", "source": "room", "member_id": "3", "gift_id": "g2", "gift_name": "旧礼物", "count": 9, "score": 9.0, "records": 1},
    ],
}


class ScoreAllMembersApiTests(unittest.TestCase):
    def test_default_season_is_latest(self) -> None:
        self.assertEqual(_season_key(BOARD, ""), "2026-winter")
        self.assertEqual(_season_key(BOARD, "2026-summer"), "2026-summer")
        with self.assertRaises(HTTPException):
            _season_key(BOARD, "2025-spring")

    def test_team_filter_and_aggregation(self) -> None:
        cells = _filter_cells(
            BOARD,
            season="2026-winter",
            group="SNH48",
            team="HII",
            member="",
            gift_name="",
            source="all",
            date_from="",
            date_to="",
        )
        self.assertEqual(len(cells), 2)
        result = _aggregate(BOARD, cells)
        self.assertEqual(result["summary"]["members"], 1)
        self.assertEqual(result["summary"]["total_score"], 7.0)
        self.assertEqual(result["summary"]["room_score"], 5.0)
        self.assertEqual(result["summary"]["live_score"], 2.0)
        member = result["members"][0]
        self.assertEqual(member["member_id"], "1")
        self.assertEqual(member["team_label"], "HII队")
        self.assertEqual(member["gifts"][0]["gift_name"], "弦月回响")
        self.assertEqual(member["gifts"][0]["score"], 7.0)

    def test_date_and_source_filters(self) -> None:
        cells = _filter_cells(
            BOARD,
            season="2026-winter",
            group="",
            team="",
            member="乙",
            gift_name="弦月回响",
            source="room",
            date_from="2026-10-25",
            date_to="2026-10-25",
        )
        self.assertEqual(len(cells), 1)
        result = _aggregate(BOARD, cells)
        self.assertEqual(result["members"][0]["member_name"], "乙")
        self.assertEqual(result["summary"]["total_score"], 3.0)

    def test_gnz_source_and_provenance_aggregation(self) -> None:
        board = dict(BOARD)
        board["cells"] = list(BOARD["cells"]) + [
            {
                "season": "2026-winter",
                "date": "2026-10-24",
                "source": "gnz",
                "member_id": "1",
                "gift_id": "g1",
                "gift_name": "弦月回响",
                "count": 4,
                "score": 4.0,
                "records": 1,
                "provenance": "gnz.hk",
            }
        ]
        board["provenance_summary"] = {"gnz.hk": {"cells": 1, "score": 4.0, "members": 1}}
        cells = _filter_cells(
            board,
            season="2026-winter",
            group="",
            team="",
            member="",
            gift_name="",
            source="gnz",
            date_from="",
            date_to="",
        )
        self.assertEqual(len(cells), 1)
        result = _aggregate(board, cells)
        self.assertEqual(result["summary"]["gnz_score"], 4.0)
        member = result["members"][0]
        self.assertEqual(member["gnz_score"], 4.0)
        self.assertEqual(member["gifts"][0]["gnz_score"], 4.0)
        self.assertEqual(member["gifts"][0]["provenance"], ["gnz.hk"])

    def test_xox_source_and_third_party_aggregation(self) -> None:
        board = dict(BOARD)
        board["cells"] = list(BOARD["cells"]) + [
            {
                "season": "2026-winter",
                "date": "2026-10-26",
                "source": "xox",
                "member_id": "1",
                "gift_id": "g1",
                "gift_name": "弦月回响",
                "count": 3,
                "score": 3.0,
                "records": 1,
                "provenance": "xox48",
            }
        ]
        board["provenance_summary"] = {"xox48": {"cells": 1, "score": 3.0, "members": 1}}
        cells = _filter_cells(
            board,
            season="2026-winter",
            group="",
            team="",
            member="",
            gift_name="",
            source="xox",
            date_from="",
            date_to="",
        )
        self.assertEqual(len(cells), 1)
        result = _aggregate(board, cells)
        self.assertEqual(result["summary"]["third_party_score"], 3.0)
        member = result["members"][0]
        self.assertEqual(member["third_party_score"], 3.0)
        self.assertEqual(member["gifts"][0]["third_party_score"], 3.0)
        self.assertEqual(member["gifts"][0]["provenance"], ["xox48"])

    def test_realtime_overlay_replaces_today_cells(self) -> None:
        import website.score_all_members_api as api

        with tempfile.TemporaryDirectory() as tmp:
            board_path = Path(tmp) / "score_board.json"
            overlay_path = Path(tmp) / "realtime_cells.json"
            board = {
                **BOARD,
                "generated_at": "2026-11-13 10:00:00",
                "cells": [
                    {"season": "2026-winter", "date": "2026-11-13", "source": "room", "member_id": "1", "gift_id": "g1", "gift_name": "弦月回响", "count": 1, "score": 1.0, "records": 1},
                    {"season": "2026-winter", "date": "2026-11-12", "source": "room", "member_id": "1", "gift_id": "g1", "gift_name": "弦月回响", "count": 2, "score": 2.0, "records": 1},
                ],
            }
            overlay = {
                "date": "2026-11-13",
                "season": "2026-winter",
                "generated_at": "2026-11-13 10:00:05",
                "cells": [
                    {"season": "2026-winter", "date": "2026-11-13", "source": "room", "member_id": "1", "gift_id": "g1", "gift_name": "弦月回响", "count": 5, "score": 5.0, "records": 3}
                ],
            }
            board_path.write_text(json.dumps(board), encoding="utf-8")
            overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
            old_path = cfg.SCORE_ALL_MEMBERS_DATA_PATH
            cfg.SCORE_ALL_MEMBERS_DATA_PATH = str(board_path)
            api._cache_path = ""
            api._cache_mtime_ns = -1
            api._cache_overlay_mtime_ns = -1
            try:
                loaded = _load_board()
            finally:
                cfg.SCORE_ALL_MEMBERS_DATA_PATH = old_path
                api._cache_path = ""
                api._cache_mtime_ns = -1
                api._cache_overlay_mtime_ns = -1
        today = [c for c in loaded["cells"] if c["date"] == "2026-11-13"]
        self.assertEqual(len(today), 1)
        self.assertEqual(today[0]["score"], 5.0)
        self.assertEqual(loaded["generated_at"], "2026-11-13 10:00:05")

    def test_qualification_filter_and_official_team_overlay(self) -> None:
        board = {
            **BOARD,
            "qualification": {
                "qualified_ids": ["1"],
                "participant_ids": ["1", "2"],
                "members": {"1": {"song": "迭代（THE GHOST）"}},
            },
            "official_teams": {
                "members": {
                    "1": {"group": "SNH48", "team": "HII", "team_label": "HII队"},
                    "2": {"group": "SNH48", "team": "预备生", "team_label": "预备生"},
                }
            },
        }
        qualified_cells = _filter_cells(
            board,
            season="2026-winter",
            group="",
            team="",
            member="",
            gift_name="",
            source="all",
            date_from="",
            date_to="",
            qualification="qualified",
        )
        self.assertEqual({cell["member_id"] for cell in qualified_cells}, {"1"})
        qualified = _aggregate(board, qualified_cells)["members"][0]
        self.assertEqual(qualified["qualification"], "qualified")
        self.assertEqual(qualified["qualification_song"], "迭代（THE GHOST）")
        self.assertEqual(qualified["team_label"], "HII队")

        not_qualified_cells = _filter_cells(
            board,
            season="2026-winter",
            group="",
            team="预备生",
            member="",
            gift_name="",
            source="all",
            date_from="",
            date_to="",
            qualification="not_qualified",
        )
        self.assertEqual([cell["member_id"] for cell in not_qualified_cells], ["2"])
        not_qualified = _aggregate(board, not_qualified_cells)["members"][0]
        self.assertEqual(not_qualified["qualification"], "not_qualified")
        self.assertEqual(not_qualified["team"], "预备生")

        facets = _facets(board, "2026-winter")
        self.assertEqual(facets["qualification_counts"]["qualified"], 1)
        self.assertEqual(facets["qualification_counts"]["not_qualified"], 1)

        # Qualification is season-scoped: the summer view must not inherit the winter badge.
        winter_only = {**board, "qualification": {**board["qualification"], "season": "2026-winter"}}
        summer_cells = _filter_cells(
            winter_only,
            season="2026-summer",
            group="",
            team="",
            member="",
            gift_name="",
            source="all",
            date_from="",
            date_to="",
            qualification="qualified",
        )
        self.assertEqual(summer_cells, [])

    def test_affiliation_overlay_and_unit_filter(self) -> None:
        board = {
            **BOARD,
            "qualification": {
                "qualified_ids": ["1", "2"],
                "participant_ids": ["1", "2", "3"],
                "members": {},
            },
            "official_teams": {
                "members": {
                    "1": {"group": "SNH48", "team": "预备生", "team_label": "预备生"},
                    "2": {"group": "SNH48", "team": "SII", "team_label": "SII队"},
                    "3": {"group": "GNZ48", "team": "G", "team_label": "G队"},
                }
            },
            "affiliation": {
                "season": "2026-winter",
                "stage_label": "红蓝歌会第一阶段",
                "units": [
                    {"key": "SNH-HII", "label": "SNH48 TEAM HII", "group": "SNH48", "slots": 8, "qualified": 1, "participants": 1, "qualified_trainees": 0},
                    {"key": "SNH-SII", "label": "SNH48 TEAM SII", "group": "SNH48", "slots": 8, "qualified": 1, "participants": 1, "qualified_trainees": 0},
                ],
                "members": {
                    "1": {
                        "trainee": True,
                        "affiliation_team": "HII",
                        "affiliation_label": "HII队",
                        "unit": "SNH-HII",
                        "unit_label": "SNH48 TEAM HII",
                    },
                    "2": {"trainee": False, "affiliation_team": "", "affiliation_label": "", "unit": "SNH-SII", "unit_label": "SNH48 TEAM SII"},
                    "3": {"trainee": False, "affiliation_team": "", "affiliation_label": "", "unit": "", "unit_label": ""},
                },
            },
        }
        cells = _filter_cells(
            board,
            season="2026-winter",
            group="",
            team="",
            member="",
            gift_name="",
            source="all",
            date_from="",
            date_to="",
            unit="SNH-HII",
        )
        self.assertEqual({cell["member_id"] for cell in cells}, {"1"})
        row = _aggregate(board, cells)["members"][0]
        self.assertTrue(row["trainee"])
        self.assertEqual(row["affiliation_team"], "HII")
        self.assertEqual(row["affiliation_label"], "HII队")
        self.assertEqual(row["affiliation_status"], "official")
        self.assertEqual(row["unit"], "SNH-HII")
        self.assertEqual(row["unit_label"], "SNH48 TEAM HII")
        # 官方所属仍是「预备生」，不被挂靠改写
        self.assertEqual(row["team"], "预备生")

        facets = _facets(board, "2026-winter")
        self.assertTrue(facets["affiliation_available"])
        self.assertEqual([unit["key"] for unit in facets["units"]], ["SNH-HII", "SNH-SII"])

        # 挂靠与晋级单元只属于 2026-winter，夏季视图不继承
        summer = _facets(board, "2026-summer")
        self.assertEqual(summer["units"], [])
        self.assertFalse(summer["affiliation_available"])

    def test_affiliation_marks_unlisted_trainee(self) -> None:
        board = {
            **BOARD,
            "affiliation": {
                "season": "2026-winter",
                "members": {"2": {"trainee": True, "affiliation_team": "", "unit": "BEJ48", "unit_label": "BEJ48"}},
            },
        }
        cells = _filter_cells(
            board,
            season="2026-winter",
            group="",
            team="SII",
            member="",
            gift_name="",
            source="all",
            date_from="",
            date_to="",
        )
        row = _aggregate(board, cells)["members"][0]
        self.assertTrue(row["trainee"])
        self.assertEqual(row["affiliation_status"], "unlisted")
        self.assertEqual(row["unit"], "BEJ48")

    def test_composite_team_and_participation_team_filters(self) -> None:
        board = {
            **BOARD,
            "affiliation": {
                "season": "2026-winter",
                "members": {
                    "1": {
                        "trainee": True,
                        "affiliation_team": "HII",
                        "affiliation_label": "HII队",
                        "participation_team": "HII",
                        "participation_team_label": "HII队",
                        "unit": "SNH-HII",
                        "unit_label": "SNH48 TEAM HII",
                        "unit_rank": 3,
                        "official_qualified": True,
                    },
                    "2": {
                        "trainee": False,
                        "participation_team": "SII",
                        "participation_team_label": "SII队",
                        "unit": "SNH-SII",
                        "unit_label": "SNH48 TEAM SII",
                    },
                },
            },
        }
        # 不带团前缀的旧参数继续可用
        self.assertEqual(
            {c["member_id"] for c in _filter_cells(
                board, season="2026-winter", group="", team="SII", member="", gift_name="",
                source="all", date_from="", date_to="",
            )},
            {"2"},
        )
        # 复合值（团|队）消除不同团同名的「预备生」歧义
        self.assertEqual(
            {c["member_id"] for c in _filter_cells(
                board, season="2026-winter", group="", team="SNH48|SII", member="", gift_name="",
                source="all", date_from="", date_to="",
            )},
            {"2"},
        )
        self.assertEqual(
            _filter_cells(
                board, season="2026-winter", group="", team="GNZ48|SII", member="", gift_name="",
                source="all", date_from="", date_to="",
            ),
            [],
        )
        # 参赛队伍按挂靠后的队伍归类
        self.assertEqual(
            {c["member_id"] for c in _filter_cells(
                board, season="2026-winter", group="", team="", member="", gift_name="",
                source="all", date_from="", date_to="", participation_team="SNH48|HII",
            )},
            {"1"},
        )
        facets = _facets(board, "2026-winter")
        self.assertIn("SNH48|SII", {item["key"] for item in facets["teams"]})
        self.assertEqual(
            {item["key"] for item in facets["participation_teams"]},
            {"SNH48|HII", "SNH48|SII"},
        )

    def test_team_distribution_estimated_and_participation_grouping(self) -> None:
        board = {
            "latest_season": "2026-winter",
            "seasons": {"2026-winter": {"key": "2026-winter", "label": "2026 红蓝歌会"}},
            "members": [
                {"member_id": "1", "member_name": "甲", "group": "SNH48", "team": "HII", "team_label": "HII队"},
                {"member_id": "2", "member_name": "乙", "group": "SNH48", "team": "预备生", "team_label": "预备生"},
                {"member_id": "3", "member_name": "丙", "group": "SNH48", "team": "SII", "team_label": "SII队"},
                {"member_id": "5", "member_name": "戊", "group": "SNH48", "team": "SII", "team_label": "SII队"},
            ],
            "cells": [
                {"season": "2026-winter", "member_id": "1", "score": 100.0},
                {"season": "2026-winter", "member_id": "2", "score": 40.0},
                {"season": "2026-winter", "member_id": "3", "score": 60.0},
                {"season": "2026-winter", "member_id": "5", "score": 90.0},
            ],
            "affiliation": {
                "season": "2026-winter",
                "units": [{"key": "SNH-HII", "label": "SNH48 TEAM HII"}, {"key": "SNH-SII", "label": "SNH48 TEAM SII"}],
                "members": {
                    "1": {"participation_team": "HII", "participation_team_label": "HII队", "unit": "SNH-HII", "unit_rank": 1},
                    "2": {
                        "trainee": True,
                        "affiliation_team": "HII",
                        "affiliation_label": "HII队",
                        "participation_team": "HII",
                        "participation_team_label": "HII队",
                        "unit": "SNH-HII",
                        "unit_rank": 2,
                    },
                    "3": {"participation_team": "SII", "participation_team_label": "SII队", "unit": "SNH-SII", "unit_rank": 1},
                    "5": {"unit": "SNH-HII", "unit_rank": 0},
                },
            },
        }
        visible_totals, estimates = _estimate_context(board, "2026-winter")
        cells = _filter_cells(
            board, season="2026-winter", group="", team="", member="",
            gift_name="", source="all", date_from="", date_to="",
        )
        result = _aggregate(
            board,
            cells,
            season="2026-winter",
            estimated_totals=_merge_estimated_totals(visible_totals, estimates),
        )
        teams = {row["team_label"]: row for row in result["team_distribution"]}
        # 官方队伍：挂靠预备生仍留在「预备生」行，估计分按完整赛季反推结果累加
        self.assertEqual(teams["HII队"]["score"], 100.0)
        self.assertEqual(teams["HII队"]["estimated_score"], 100.0)
        self.assertEqual(teams["预备生"]["score"], 40.0)
        self.assertEqual(teams["预备生"]["estimated_score"], 90.0)
        self.assertEqual(teams["SII队"]["score"], 150.0)
        self.assertEqual(teams["SII队"]["estimated_score"], 150.0)
        participation = {
            row["participation_team_label"]: row
            for row in result["participation_team_distribution"]
        }
        # 参赛队伍：挂靠预备生并入挂靠队
        self.assertEqual(participation["HII队"]["score"], 140.0)
        self.assertEqual(participation["HII队"]["estimated_score"], 190.0)
        self.assertEqual(participation["HII队"]["members"], 2)
        self.assertEqual(participation["SII队"]["score"], 60.0)
        # 有赛季计分但不在参赛名单/无参赛队伍的成员归到「未参赛」
        self.assertEqual(participation["未参赛"]["score"], 90.0)
        self.assertEqual(participation["未参赛"]["estimated_score"], 90.0)

    def test_official_rank_is_exposed_on_rows(self) -> None:
        board = {
            **BOARD,
            "affiliation": {
                "season": "2026-winter",
                "official_result": {
                    "announced_at": "2026-11-16 09:00",
                    "post_url": "https://weibo.com/2689280541/5365803886053511",
                    "order_note": "官方名单每个队伍从左到右为第一阶段队内计分由高到低",
                    "units": {"SNH-HII": ["甲"]},
                },
                "members": {
                    "1": {
                        "unit": "SNH-HII",
                        "unit_label": "SNH48 TEAM HII",
                        "unit_rank": 5,
                        "official_qualified": True,
                    }
                },
                "units": [
                    {
                        "key": "SNH-HII",
                        "label": "SNH48 TEAM HII",
                        "group": "SNH48",
                        "slots": 8,
                        "qualified": 1,
                        "participants": 1,
                        "qualified_trainees": 0,
                        "official_order": ["甲"],
                    }
                ],
            },
        }
        cells = _filter_cells(
            board, season="2026-winter", group="", team="HII", member="", gift_name="",
            source="all", date_from="", date_to="",
        )
        row = _aggregate(board, cells)["members"][0]
        self.assertEqual(row["unit_rank"], 5)
        self.assertTrue(row["official_qualified"])
        facets = _facets(board, "2026-winter")
        self.assertEqual(facets["units"][0]["official_order"], ["甲"])

    def test_official_event_period_overrides_snapshot(self) -> None:
        board = {
            **BOARD,
            "members": [
                {**item, "period_name": "SNH48 一期生"} for item in BOARD["members"]
            ],
            "qualification": {
                "members": {"1": {"official_event_period": "BEJ48 十九期生"}},
            },
        }
        cells = _filter_cells(
            board, season="2026-winter", group="", team="", member="", gift_name="",
            source="all", date_from="", date_to="",
        )
        rows = {row["member_id"]: row for row in _aggregate(board, cells)["members"]}
        self.assertEqual(rows["1"]["period_name"], "BEJ48 十九期生")
        # 没有官方期数的成员继续使用快照值
        self.assertEqual(rows["2"]["period_name"], "SNH48 一期生")

    def test_fan_payload_reads_member_detail(self) -> None:
        board = {
            **BOARD,
            "fan_scores": {
                "generated_at": "2026-11-16 10:22:00",
                "fan_limit": 200,
                "seasons": {
                    "2026-winter": {
                        "members": {
                            "1": {
                                "member_id": "1",
                                "member_name": "甲",
                                "fan_count": 2,
                                "total_score": 12.0,
                                "fans": [
                                    {"fan_id": "f2", "fan_name": "乙", "score": 9.0, "count": 9, "records": 2, "room_score": 9.0, "live_score": 0.0, "gifts": []},
                                    {"fan_id": "f1", "fan_name": "甲", "score": 3.0, "count": 3, "records": 1, "room_score": 3.0, "live_score": 0.0, "gifts": []},
                                ],
                            }
                        }
                    }
                },
            },
        }
        payload = _fan_payload(board, "2026-winter", "1")
        self.assertEqual(payload["member_name"], "甲")
        self.assertEqual(payload["fan_count"], 2)
        self.assertEqual(payload["total_score"], 12.0)
        self.assertEqual([fan["fan_id"] for fan in payload["fans"]], ["f2", "f1"])
        self.assertFalse(payload["truncated"])
        empty = _fan_payload(board, "2026-winter", "404")
        self.assertEqual(empty["fans"], [])
        self.assertEqual(empty["fan_count"], 0)

    def test_missing_gift_id_merges_by_gift_name(self) -> None:
        board = dict(BOARD)
        board["cells"] = list(BOARD["cells"]) + [
            {
                "season": "2026-winter",
                "date": "2026-10-26",
                "source": "room",
                "member_id": "1",
                "gift_id": "",
                "gift_name": "弦月回响",
                "count": 1,
                "score": 1.0,
                "records": 1,
            }
        ]
        cells = _filter_cells(
            board,
            season="2026-winter",
            group="",
            team="",
            member="",
            gift_name="",
            source="all",
            date_from="",
            date_to="",
        )
        result = _aggregate(board, cells, season="2026-winter")
        matching = [gift for gift in result["gift_distribution"] if gift["gift_name"] == "弦月回响"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["score"], 11.0)

    def test_gift_and_team_facets(self) -> None:
        facets = _facets(BOARD, "2026-winter")
        self.assertEqual(facets["groups"], ["SNH48"])
        self.assertIn(
            {"key": "SNH48|HII", "group": "SNH48", "team": "HII", "team_label": "HII队"},
            facets["teams"],
        )
        self.assertEqual([gift["gift_name"] for gift in facets["gifts"]], ["弦月回响"])

    def test_score_gift_season_paths(self) -> None:
        with mock.patch.object(cfg, "SCORE_GIFTS_DATA_PATH", "/tmp/summer.json"), mock.patch.object(
            cfg, "SCORE_GIFTS_WINTER_DATA_PATH", "/tmp/winter.json"
        ):
            self.assertEqual(_data_path("2026-summer"), Path("/tmp/summer.json"))
            self.assertEqual(_data_path("2026-winter"), Path("/tmp/winter.json"))
            with self.assertRaises(HTTPException):
                _data_path("2025-spring")

    def test_score_pages_format_at_most_one_decimal(self) -> None:
        """计分数据最多一位小数，页面不应格式化出更多小数位。"""
        templates = Path(__file__).resolve().parents[1] / "website" / "templates"
        for name in ("score_all_members.html", "score_gifts.html"):
            with self.subTest(template=name):
                source = (templates / name).read_text(encoding="utf-8")
                self.assertIn("maximumFractionDigits: 1", source)
                self.assertNotIn("maximumFractionDigits: 6", source)


DARK_BOARD = {
    "season": "2026-winter",
    "cells": [
        {"season": "2026-winter", "member_id": "1", "score": 100.0},
        {"season": "2026-winter", "member_id": "2", "score": 60.0},
        {"season": "2026-winter", "member_id": "3", "score": 40.0},
        {"season": "2026-winter", "member_id": "4", "score": 30.0},
        {"season": "2026-winter", "member_id": "5", "score": 90.0},
        {"season": "2026-winter", "member_id": "6", "score": 40.0},
        {"season": "2026-summer", "member_id": "1", "score": 999.0},
    ],
    "affiliation": {
        "season": "2026-winter",
        "members": {
            "1": {"unit": "SNH-HII", "unit_rank": 1},
            "2": {"unit": "SNH-HII", "unit_rank": 2},
            "3": {"unit": "SNH-HII", "unit_rank": 3},
            "4": {"unit": "SNH-HII", "unit_rank": 0},
            "5": {"unit": "SNH-HII", "unit_rank": 0},
            "6": {"unit": "", "unit_rank": 0},
        },
        "units": [{"key": "SNH-HII", "label": "SNH48 TEAM HII"}],
    },
}


class DarkVoteEstimateTests(unittest.TestCase):
    def test_season_visible_totals_ignore_other_seasons(self) -> None:
        totals = _season_visible_totals(DARK_BOARD, "2026-winter")
        self.assertEqual(totals["1"], 100.0)
        self.assertNotIn(999.0, totals.values())

    def test_unit_rank_estimates_walk_bottom_up(self) -> None:
        totals = _season_visible_totals(DARK_BOARD, "2026-winter")
        estimates = _unit_rank_estimates(DARK_BOARD, "2026-winter", totals)
        # 未晋级最高明票 90 是晋级末位（第 3 名 40）的下界。
        self.assertEqual(estimates["3"]["dark_min_score"], 50.0)
        self.assertEqual(estimates["3"]["estimated_total_score"], 90.0)
        # 第 2 名明票 60 低于第 3 名的估计 90，用暗票补到 90。
        self.assertEqual(estimates["2"]["dark_min_score"], 30.0)
        self.assertEqual(estimates["2"]["estimated_total_score"], 90.0)
        # 第 1 名明票 100 已经高于下界，不需要暗票。
        self.assertEqual(estimates["1"]["dark_min_score"], 0.0)
        self.assertEqual(estimates["1"]["estimated_total_score"], 100.0)
        self.assertTrue(estimates["3"]["ranked_in_unit"])
        # 未晋级成员没有排名约束，最少暗票为 0。
        self.assertFalse(estimates["4"]["ranked_in_unit"])
        self.assertEqual(estimates["4"]["dark_min_score"], 0.0)
        # 无参赛单元的成员不参与反推。
        self.assertNotIn("6", estimates)

    def test_unqualified_visible_score_lifts_qualified_floor(self) -> None:
        board = {
            **DARK_BOARD,
            "cells": [
                cell for cell in DARK_BOARD["cells"] if cell["member_id"] != "5"
            ]
            + [{"season": "2026-winter", "member_id": "5", "score": 260.0}],
        }
        totals = _season_visible_totals(board, "2026-winter")
        estimates = _unit_rank_estimates(board, "2026-winter", totals)
        # 未晋级成员最高明票 260，晋级末位（第 3 名 40）至少要 260。
        self.assertEqual(estimates["3"]["estimated_total_score"], 260.0)
        self.assertEqual(estimates["3"]["dark_min_score"], 220.0)
        # 第 2 名、第 1 名被继续顶高。
        self.assertEqual(estimates["2"]["estimated_total_score"], 260.0)
        self.assertEqual(estimates["1"]["estimated_total_score"], 260.0)
        self.assertEqual(estimates["1"]["dark_min_score"], 160.0)

    def test_estimates_skip_other_seasons(self) -> None:
        totals = _season_visible_totals(DARK_BOARD, "2026-winter")
        self.assertEqual(
            _unit_rank_estimates(DARK_BOARD, "2026-summer", totals),
            {},
        )

    def test_attach_dark_estimates_adds_row_fields(self) -> None:
        board = {**DARK_BOARD, "members": []}
        cells = _filter_cells(
            board, season="2026-winter", group="", team="", member="",
            gift_name="", source="all", date_from="", date_to="",
        )
        rows = _aggregate(board, cells)["members"]
        _attach_dark_estimates(board, rows, "2026-winter")
        by_id = {row["member_id"]: row for row in rows}
        self.assertEqual(by_id["1"]["dark_min_score"], 0.0)
        self.assertEqual(by_id["1"]["estimated_total_score"], 100.0)
        self.assertEqual(by_id["1"]["visible_total_score"], 100.0)
        self.assertTrue(by_id["1"]["ranked_in_unit"])
        # 无排名的非参赛成员：暗票未知（None），估计总分退化为明票。
        self.assertIsNone(by_id["6"]["dark_min_score"])
        self.assertEqual(by_id["6"]["estimated_total_score"], 40.0)
        self.assertFalse(by_id["6"]["ranked_in_unit"])


if __name__ == "__main__":
    unittest.main()

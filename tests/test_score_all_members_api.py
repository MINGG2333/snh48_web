from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from website import config as cfg
from website.score_all_members_api import (
    _aggregate,
    _facets,
    _filter_cells,
    _season_key,
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

    def test_gift_and_team_facets(self) -> None:
        facets = _facets(BOARD, "2026-winter")
        self.assertEqual(facets["groups"], ["SNH48"])
        self.assertIn({"group": "SNH48", "team": "HII", "team_label": "HII队"}, facets["teams"])
        self.assertEqual([gift["gift_name"] for gift in facets["gifts"]], ["弦月回响"])

    def test_score_gift_season_paths(self) -> None:
        with mock.patch.object(cfg, "SCORE_GIFTS_DATA_PATH", "/tmp/summer.json"), mock.patch.object(
            cfg, "SCORE_GIFTS_WINTER_DATA_PATH", "/tmp/winter.json"
        ):
            self.assertEqual(_data_path("2026-summer"), Path("/tmp/summer.json"))
            self.assertEqual(_data_path("2026-winter"), Path("/tmp/winter.json"))
            with self.assertRaises(HTTPException):
                _data_path("2025-spring")


if __name__ == "__main__":
    unittest.main()

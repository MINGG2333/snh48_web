from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from website import pk_score_api


class PkScoreApiTests(unittest.TestCase):
    def setUp(self) -> None:
        pk_score_api._cache_doc = {}
        pk_score_api._cache_mtime_ns = -1

    def test_loads_valid_derived_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "current.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "competitors": [{"name": "甲"}, {"name": "乙"}],
                        "items": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with mock.patch.object(pk_score_api.cfg, "PK_SCORE_DATA_PATH", str(path)):
                self.assertEqual(pk_score_api._load_dataset()["competitors"][0]["name"], "甲")

    def test_rejects_invalid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "current.json"
            path.write_text('{"version": 1, "competitors": [], "items": []}', encoding="utf-8")
            with mock.patch.object(pk_score_api.cfg, "PK_SCORE_DATA_PATH", str(path)):
                with self.assertRaises(HTTPException) as raised:
                    pk_score_api._load_dataset()
            self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()

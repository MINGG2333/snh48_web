from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import Response

from website import config as cfg
from website import identity_index
from website import redblue_ledger_api


class IdentityIndexCacheTests(unittest.TestCase):
    def test_fallback_changes_do_not_invalidate_primary_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "identity.json"
            fallback = root / "fallback.json"
            primary.write_text(
                json.dumps({"accounts": {"1001": {"latest_name": "小甲"}}}, ensure_ascii=False),
                encoding="utf-8",
            )
            fallback.write_text(json.dumps({"nicknames": []}), encoding="utf-8")
            old_path = cfg.REDBLUE_IDENTITY_INDEX_PATH
            old_fallback = cfg.REDBLUE_IDENTITY_FALLBACK_PATHS
            cfg.REDBLUE_IDENTITY_INDEX_PATH = str(primary)
            cfg.REDBLUE_IDENTITY_FALLBACK_PATHS = {
                "sender_identity_map": str(fallback),
                "sender_profiles": "",
                "fan_name_map": "",
            }
            identity_index.clear_cache()
            try:
                with mock.patch.object(identity_index, "_build", wraps=identity_index._build) as build:
                    first = identity_index.redblue_index()
                    fallback.write_text(json.dumps({"nicknames": [{"sender_name": "新名"}]}), encoding="utf-8")
                    second = identity_index.redblue_index()
                self.assertEqual(build.call_count, 1)
                self.assertIs(first["by_id"], second["by_id"])
                self.assertEqual(identity_index.latest_names_by_id()["1001"], "小甲")
            finally:
                cfg.REDBLUE_IDENTITY_INDEX_PATH = old_path
                cfg.REDBLUE_IDENTITY_FALLBACK_PATHS = old_fallback
                identity_index.clear_cache()

    def test_redblue_data_read_does_not_trigger_room_live_sync(self) -> None:
        with mock.patch.object(
            redblue_ledger_api,
            "_load_filtered",
            return_value=({"entries": [], "aliases": []}, []),
        ), mock.patch.object(redblue_ledger_api, "_sync_room_live_now") as sync:
            payload = redblue_ledger_api.get_redblue_data(
                response=Response(),
                source="all",
                status_filter="all",
                keyword="",
                date_from="",
                date_to="",
                sort="time_asc",
                include_duplicate=True,
                _=True,
            )
        sync.assert_not_called()
        self.assertEqual(payload["entries"], [])


if __name__ == "__main__":
    unittest.main()

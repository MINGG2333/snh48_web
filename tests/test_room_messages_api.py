from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import Response

from website import room_messages_api as api


def _row(row_id: str, sender: str = "Alice", text: str = "hello") -> dict:
    return {
        "id": row_id,
        "bj_time": "2026-01-01 12:00:00",
        "date": "2026-01-01",
        "msg_type": "TEXT",
        "sender_name": sender,
        "sender_id": "1",
        "raw_content": text,
        "media_url": "",
        "media_path": "",
        "room_type": "main",
        "family": "text",
        "_row_index": int(row_id),
    }


class RoomMessagesApiTests(unittest.TestCase):
    def test_filter_rows_uses_sender_index_and_keyword_fields(self) -> None:
        rows = [
            _row("0", "Alice", "第一条"),
            _row("1", "Bob", "第二条"),
            _row("2", "Alicia", "第三条"),
        ]
        sender_index = api._build_sender_index(rows)
        filtered = api._filter_rows(
            rows,
            msg_type="ALL",
            families=None,
            sender="ali",
            keyword="第三",
            has_media="all",
            room_type="all",
            date_from="",
            date_to="",
            sender_index=sender_index,
        )
        self.assertEqual([row["id"] for row in filtered], ["2"])

    def test_keyword_matches_audio_transcript(self) -> None:
        row = _row("0", text="语音")
        row["audio_transcript"] = {"text": "转录内容"}
        self.assertTrue(api._row_matches_keyword(row, "转录"))
        self.assertFalse(api._row_matches_keyword(row, "不存在"))

    def test_public_row_exposes_row_index_without_private_fields(self) -> None:
        item = api._public_row(_row("7"))
        self.assertEqual(item["row_index"], 7)
        self.assertNotIn("_row_index", item)

    def test_context_endpoint_returns_unfiltered_neighbours(self) -> None:
        rows = [_row("0"), _row("1"), _row("2")]
        with mock.patch.object(api, "_load_dataset", return_value=(rows, {}, {})):
            before = api.get_room_messages_context(
                response=Response(),
                message_id="1",
                direction="before",
                limit=1,
                _=True,
            )
            after = api.get_room_messages_context(
                response=Response(),
                message_id="1",
                direction="after",
                limit=1,
                _=True,
            )
        self.assertEqual([item["id"] for item in before["items"]], ["0"])
        self.assertEqual([item["id"] for item in after["items"]], ["2"])
        self.assertEqual(before["items"][0]["row_index"], 0)

    def test_stale_cache_is_served_while_refresh_runs_in_background(self) -> None:
        cached = ([_row("0")], {"total_messages": 1}, {})
        old_state = api._cache_state
        old_signature = api._cache_signature
        try:
            api._cache_state = cached
            api._cache_signature = ("old",)
            with mock.patch.object(api, "_dataset_signature", return_value=("new",)), \
                    mock.patch.object(api, "_schedule_background_refresh") as schedule:
                result = api._load_dataset()
            self.assertIs(result, cached)
            schedule.assert_called_once_with()
        finally:
            api._cache_state = old_state
            api._cache_signature = old_signature

    def test_read_jsonl_file_annotates_notices_and_strips_raw_ext_info(self) -> None:
        payload = [
            {
                "id": "notice-1",
                "bj_time": "2026-01-01 12:00:00",
                "msg_type": "QCHAT_SERVER_NOTICE",
                "sender_name": "系统",
                "sender_id": "0",
                "room_type": "main",
                "room_channel_id": "channel-1",
                "raw_extInfo": json.dumps({"serverInfo": {"3": "房间A"}}, ensure_ascii=False),
            },
            {
                "id": "delete-1",
                "bj_time": "2026-01-01 12:01:00",
                "msg_type": "DELETE",
                "reply_to": "notice-1",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "messages.jsonl"
            path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in payload) + "\n", encoding="utf-8")
            rows, annotations = api._read_jsonl_file(path, {})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["detail"], "首次观测到房间状态广播")
        self.assertNotIn("raw_extInfo", rows[0])
        self.assertEqual(annotations["deleted_ids"], {"notice-1": "2026-01-01 12:01:00"})


if __name__ == "__main__":
    unittest.main()

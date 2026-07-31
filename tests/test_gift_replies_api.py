from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException, Response

from website.gift_replies_api import (
    _group_rows_by_sender,
    get_gift_reply_sender_history,
    get_gift_reply_senders,
    router,
)


def gift(
    message_id: str,
    gift_time: str,
    sender_id: str,
    sender_name: str,
    *,
    has_reply: bool,
    gift_count: int = 1,
) -> dict[str, object]:
    return {
        "gift_message_id": message_id,
        "gift_bj_time": gift_time,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "gift_name": "测试礼物",
        "gift_count": gift_count,
        "has_reply": has_reply,
        "reply_status": "replied" if has_reply else "unreplied",
    }


class GiftReplyGroupingTests(unittest.TestCase):
    def test_groups_by_sender_id_and_orders_groups_and_history_newest_first(self) -> None:
        groups = _group_rows_by_sender(
            [
                gift("a-old", "2026-07-01 10:00:00", "100", "旧昵称", has_reply=True),
                gift("b", "2026-07-03 10:00:00", "200", "用户乙", has_reply=False),
                gift("a-new", "2026-07-04 10:00:00", "100", "新昵称", has_reply=False, gift_count=3),
            ]
        )

        self.assertEqual([group["sender_id"] for group in groups], ["100", "200"])
        sender = groups[0]
        self.assertEqual(sender["sender_name"], "新昵称")
        self.assertEqual([item["gift_message_id"] for item in sender["items"]], ["a-new", "a-old"])
        self.assertEqual(sender["total_messages"], 2)
        self.assertEqual(sender["total_gift_count"], 4)
        self.assertEqual(sender["replied_messages"], 1)
        self.assertEqual(sender["unreplied_messages"], 1)
        self.assertEqual(sender["sender_key"], "id:100")

    def test_uses_most_recent_nonempty_name_for_a_known_sender_id(self) -> None:
        groups = _group_rows_by_sender(
            [
                gift("new", "2026-07-04 10:00:00", "100", "", has_reply=False),
                gift("old", "2026-07-01 10:00:00", "100", "可用昵称", has_reply=True),
            ]
        )
        self.assertEqual(groups[0]["sender_name"], "可用昵称")


class GiftReplySendersApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        rows = [
            gift("new", "2026-07-04 10:00:00", "100", "用户甲", has_reply=False, gift_count=2),
            gift("old", "2026-07-01 10:00:00", "100", "用户甲旧昵称", has_reply=True),
            gift("done", "2026-07-03 10:00:00", "200", "用户乙", has_reply=True),
            gift("before-default", "2026-05-29 23:59:59", "100", "更早昵称", has_reply=False),
            gift("before-only", "2026-05-01 10:00:00", "300", "用户丙", has_reply=False),
        ]
        fields = [
            "gift_message_id",
            "gift_bj_time",
            "sender_id",
            "sender_name",
            "gift_name",
            "gift_count",
            "has_reply",
            "reply_status",
        ]
        with (self.data_dir / "gifts.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                csv_row = dict(row)
                csv_row["has_reply"] = "1" if row["has_reply"] else "0"
                writer.writerow(csv_row)
        (self.data_dir / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-07-31 12:00:00",
                    "refresh_interval_seconds": 30,
                    "summary": {"unreplied_gift_messages": 1},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.patches = [mock.patch("website.gift_replies_api.cfg.GIFT_REPLIES_DIR", str(self.data_dir))]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def call_endpoint(
        self,
        *,
        status: str = "unreplied",
        sender: str = "",
        date_from: str = "2026-05-30",
        date_to: str = "",
    ) -> dict[str, object]:
        return get_gift_reply_senders(
            Response(),
            status_filter=status,
            sender=sender,
            date_from=date_from,
            date_to=date_to,
            _=True,
        )

    def test_defaults_to_date_filtered_unreplied_sender_summaries_without_history(self) -> None:
        payload = self.call_endpoint()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["sender_summary"]["total_senders"], 2)
        self.assertEqual(payload["sender_summary"]["senders_with_unreplied"], 1)
        self.assertEqual(payload["date_from"], "2026-05-30")
        self.assertNotIn("items", payload["items"][0])
        self.assertEqual(payload["items"][0]["total_messages"], 2)
        self.assertEqual(payload["summary"]["unreplied_gift_messages"], 1)

    def test_can_search_an_old_nickname_and_rejects_invalid_status(self) -> None:
        payload = self.call_endpoint(status="all", sender="旧昵称")
        self.assertEqual(payload["items"][0]["sender_id"], "100")
        with self.assertRaises(HTTPException) as raised:
            self.call_endpoint(status="invalid")
        self.assertEqual(raised.exception.status_code, 422)

    def test_date_filter_changes_sender_set_and_rejects_invalid_range(self) -> None:
        payload = self.call_endpoint(status="all", date_from="2026-05-01", date_to="2026-05-29")
        self.assertEqual([item["sender_id"] for item in payload["items"]], ["100", "300"])
        with self.assertRaises(HTTPException) as raised:
            self.call_endpoint(date_from="2026-06-01", date_to="2026-05-30")
        self.assertEqual(raised.exception.status_code, 422)

    def test_sender_history_is_loaded_separately_and_uses_same_date_range(self) -> None:
        payload = get_gift_reply_sender_history(
            Response(),
            sender_key="id:100",
            date_from="2026-05-30",
            date_to="",
            _=True,
        )
        self.assertEqual(
            [item["gift_message_id"] for item in payload["item"]["items"]],
            ["new", "old"],
        )

    def test_router_registers_password_protected_sender_endpoints(self) -> None:
        for path in ("/api/gift-replies/senders", "/api/gift-replies/sender-history"):
            route = next(route for route in router.routes if route.path == path)
            self.assertTrue(route.dependant.dependencies)


class GiftReplySendersTemplateTests(unittest.TestCase):
    def test_template_uses_dom_rendering_and_tracks_key_actions(self) -> None:
        template = Path("website/templates/gift_reply_senders.html").read_text(encoding="utf-8")
        self.assertIn('/api/gift-replies/senders?', template)
        self.assertIn('/api/gift-replies/sender-history?', template)
        self.assertIn('details.open = expandedSenderKeys.has(group.sender_key)', template)
        self.assertIn('value="2026-05-30"', template)
        self.assertIn('input[type="date"]::-webkit-calendar-picker-indicator', template)
        self.assertIn('invert(79%) sepia(23%)', template)
        self.assertIn('id="statsToggle"', template)
        self.assertIn('收起该送礼人', template)
        self.assertIn('房间内回礼情况', template)
        self.assertNotIn('<h1>综合回礼</h1>', template)
        self.assertIn('collapseAndHighlightSender(details)', template)
        self.assertIn('summary.scrollIntoView', template)
        self.assertIn('"return-highlight"', template)
        self.assertIn('}, 3000)', template)
        self.assertNotIn('id="pageSizeSelect"', template)
        self.assertNotIn('class="pagination"', template)
        self.assertIn('area: "gift_reply_senders"', template)
        self.assertIn('applyFilters("filter_sender_status")', template)
        self.assertNotIn("innerHTML", template)

        room_template = Path("website/templates/room_messages.html").read_text(encoding="utf-8")
        self.assertIn('href="/room/gift-senders"', room_template)
        self.assertIn('open_combined_gift_replies', room_template)

        main = Path("website/main.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/room/gifts"', main)
        self.assertIn('@app.get("/room/gift-senders"', main)
        self.assertNotIn('@app.get("/gift-replies"', main)
        self.assertNotIn('@app.get("/gift-replies/senders"', main)
        self.assertNotIn('@app.get("/gr"', main)


if __name__ == "__main__":
    unittest.main()

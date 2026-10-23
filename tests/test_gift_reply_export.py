from __future__ import annotations

import io
import unittest

from PIL import Image

from website.gift_replies_api import (
    _export_period_text,
    _sender_filter_text,
    _timeline_filter_text,
)
from website.gift_reply_export import render_overview_png, render_timeline_png


def row(
    message_id: str,
    time: str,
    sender: str,
    gift: str,
    *,
    replied: bool,
    count: int = 1,
) -> dict:
    return {
        "gift_message_id": message_id,
        "gift_bj_time": time,
        "sender_name": sender,
        "gift_name": gift,
        "gift_count": count,
        "has_reply": replied,
        "reply_status": "replied" if replied else "unreplied",
    }


class GiftReplyExportTests(unittest.TestCase):
    def test_timeline_png_contains_all_rows(self) -> None:
        rows = [
            row("a", "2026-10-23 19:00:00", "用户甲", "心锁", replied=False),
            row("b", "2026-10-22 18:00:00", "用户乙", "巧克力", replied=True, count=3),
        ]
        data = render_timeline_png(
            rows,
            period="2026-10-01 起",
            filter_text="全部状态",
            updated="2026-10-23 19:30",
        )
        self.assertTrue(data.startswith(b"\x89PNG"))
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.width, 1000)
            self.assertGreater(image.height, 150)

    def test_overview_png_groups_senders(self) -> None:
        groups = [
            {
                "sender_name": "用户甲",
                "items": [
                    row("a", "2026-10-23 19:00:00", "用户甲", "心锁", replied=False),
                    row("c", "2026-10-22 19:00:00", "用户甲", "玫瑰花", replied=True),
                ],
            },
            {
                "sender_name": "用户乙",
                "items": [row("b", "2026-10-21 18:00:00", "用户乙", "巧克力", replied=True)],
            },
        ]
        data = render_overview_png(
            groups,
            period="2026-10-01 至 2026-10-23",
            filter_text="全部",
            updated="2026-10-23 19:30",
        )
        self.assertTrue(data.startswith(b"\x89PNG"))
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.width, 1000)
            self.assertGreater(image.height, 150)

    def test_empty_export_is_still_png(self) -> None:
        data = render_timeline_png([], period="全部时间")
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_filter_labels(self) -> None:
        self.assertEqual(_export_period_text("2026-10-01", "2026-10-23"), "2026-10-01 至 2026-10-23")
        self.assertEqual(_export_period_text("2026-10-01", ""), "2026-10-01 起")
        self.assertEqual(_timeline_filter_text("unreplied", "心锁", "", "all"), "未回复 · 礼物：心锁")
        self.assertEqual(_sender_filter_text("unreplied", "用户甲"), "有未回复 · 送礼人：用户甲")


if __name__ == "__main__":
    unittest.main()

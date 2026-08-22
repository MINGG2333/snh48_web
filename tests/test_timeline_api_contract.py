from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from website.timeline_api import router


FIELDNAMES = [
    "date", "day_of_week", "time", "type", "name", "icon", "delete", "reason",
    "source_msg_id", "updated_at", "description", "snh48_weibo_urls",
    "snh48_bilibili_urls", "location", "image_urls", "llm_analyzed", "source_url",
    "chenjiayi_weibo_urls", "cover_url", "event_type", "event_link", "event_images",
    "remark", "video_urls",
]


class TimelineApiContractTests(unittest.TestCase):
    def write_schedule(self, path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerow({"date": "2026-07-30", "type": "日常", "name": "微博状态", "event_type": "日常"})
            writer.writerow({"date": "2026-07-31", "time": "19:13", "type": "里程碑", "name": "出道300天纪念", "event_type": "里程碑"})

    def test_daily_rows_are_not_exposed_and_csv_milestone_suppresses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            schedule_path = Path(temp) / "events.csv"
            self.write_schedule(schedule_path)
            with mock.patch.object(router, "_find_schedule_csv", return_value=schedule_path):
                with mock.patch.object(router, "timeline_milestone_days", return_value=[300]), mock.patch.object(
                    router, "milestone_date", return_value=router.date(2026, 7, 31)
                ):
                    records = router.read_schedule(on_date=router.date(2026, 8, 22))
            self.assertEqual([record["title"] for record in records], ["出道300天纪念"])


if __name__ == "__main__":
    unittest.main()

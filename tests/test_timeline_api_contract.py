from __future__ import annotations

import csv
import asyncio
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
    def test_unified_index_rows_without_push_time_use_live_start_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            index = Path(temp) / "live_index.csv"
            fields = [
                "live_id", "member_name", "title", "live_type", "push_bj",
                "live_ctime_bj", "start_bj", "live_cover_url",
                "official_replay_url", "official_replay_status",
                "official_danmu_url", "official_danmu_status",
            ]
            with index.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "live_id": "unified",
                    "member_name": "陈嘉仪",
                    "title": "最新直播",
                    "live_type": "1",
                    "push_bj": "",
                    "live_ctime_bj": "2026-09-12 23:19:28",
                    "start_bj": "2026-09-12 23:19:28",
                    "live_cover_url": "/2026/0912/cover.jpg",
                    "official_replay_url": "https://idol-vod.48.cn/replay.m3u8",
                    "official_replay_status": "replaced",
                    "official_danmu_url": "https://source.48.cn/live/lrc/demo.lrc",
                    "official_danmu_status": "downloaded",
                })
            with mock.patch.object(router.cfg, "LIVE_PUSH_REPLAY_ROOT", temp), mock.patch.object(
                router.cfg, "LIVE_RECORD_ROOT", temp
            ):
                records = router.read_live_pushes()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["id"], "live_unified")
            self.assertEqual(records[0]["datetime"], "2026-09-12 23:19:28")
            self.assertEqual(records[0]["title"], "最新直播")
            self.assertTrue(records[0]["has_replay"])
            self.assertTrue(records[0]["has_danmu"])

    def test_producer_relative_danmu_path_uses_local_file_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            replay_root = Path(temp) / "replays"
            relative = Path("陈嘉仪_161808449/danmu/radio.lrc")
            local = replay_root / relative
            local.parent.mkdir(parents=True)
            content = "[00:07.53]测试弹幕\n"
            local.write_text(content, encoding="utf-8")
            with mock.patch.object(router.cfg, "LIVE_PUSH_REPLAY_ROOT", str(replay_root)), mock.patch.object(
                router, "_read_text_url", side_effect=AssertionError("local danmu must not fetch remotely")
            ), mock.patch.object(router, "_read_danmu_url_cache", return_value=None):
                self.assertEqual(router._get_danmu_text({
                    "danmu_local_path": f"live_push_replays/{relative}",
                    "danmu_url": "https://example.com/radio.lrc",
                }), content)
                self.assertEqual(router._resolve_danmu_file_path(str(local)), local)
                self.assertEqual(router._resolve_danmu_file_path(str(relative)), local)
                self.assertEqual(router._resolve_danmu_file_path("danmu/radio.lrc"), local)

    def test_radio_and_video_replays_keep_danmu_and_use_correct_player(self) -> None:
        from starlette.requests import Request
        from website import main

        with tempfile.TemporaryDirectory() as temp:
            summary = Path(temp) / "陈嘉仪_161808449" / "summary.csv"
            summary.parent.mkdir()
            fields = ["live_id", "push_bj", "title", "live_type", "play_url",
                      "video_status", "danmu_local_path", "cover_local_path"]
            with summary.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for live_id, live_type in [("video", "1"), ("radio", "2"), ("legacy", "")]:
                    writer.writerow({
                        "live_id": live_id, "push_bj": "2026-09-09 22:33:24",
                        "title": "回放", "live_type": live_type,
                        "play_url": "https://example.com/replay.m3u8",
                        "video_status": "available", "danmu_local_path": "danmu/sample.lrc",
                        "cover_local_path": "room_record/live_covers/cover.jpg",
                    })
            with mock.patch.object(router, "_get_summary_csv_path", return_value=summary):
                records = router.read_live_pushes()
            with mock.patch.object(main.cfg, "LIVE_PUSH_REPLAY_ROOT", temp):
                request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
                for record in records:
                    is_radio = record["id"] == "live_radio"
                    self.assertEqual(record["type"], "live")
                    self.assertEqual(record["source"], "room")
                    self.assertTrue(record["has_replay"])
                    self.assertTrue(record["has_danmu"])
                    self.assertEqual(record["is_radio"], is_radio)
                    self.assertEqual(record["live_type"], 2 if is_radio else 1)
                    self.assertEqual(record["typeLabel"], "电台" if is_radio else "直播")
                    self.assertIn("有回放音频" if is_radio else "有回放视频", record["description"])
                    response = asyncio.run(main.replay_page(request, record["id"][5:]))
                    html = response.body.decode()
                    self.assertIn('id="replayVideo"', html)
                    self.assertIn('id="danmuLayer"', html)
                    self.assertEqual('<div class="radio-stage">' in html, is_radio)
                    self.assertEqual('class="player-container radio-mode"' in html, is_radio)
                    if is_radio:
                        self.assertIn('src="/live-covers/cover.jpg"', html)
                        self.assertIn("电台信息", html)

    def write_schedule(self, path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerow({"date": "2026-07-30", "type": "日常", "name": "微博状态", "event_type": "日常"})
            writer.writerow({"date": "2026-07-31", "time": "19:13", "type": "里程碑", "name": "出道300天纪念", "event_type": "里程碑"})
            writer.writerow({"date": "2026-11-06", "type": "Live", "name": "Mini Live", "event_type": "行程"})

    def test_daily_rows_are_not_exposed_and_csv_milestone_suppresses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            schedule_path = Path(temp) / "events.csv"
            self.write_schedule(schedule_path)
            with mock.patch.object(router, "_find_schedule_csv", return_value=schedule_path):
                with mock.patch.object(router, "timeline_milestone_days", return_value=[300]), mock.patch.object(
                    router, "milestone_date", return_value=router.date(2026, 7, 31)
                ):
                    records = router.read_schedule(on_date=router.date(2026, 8, 22))
            self.assertEqual([record["title"] for record in records], ["出道300天纪念", "Mini Live"])
            mini_live = records[1]
            self.assertEqual(mini_live["typeLabel"], "Live")
            self.assertEqual(mini_live["timelineCategory"], "schedule")


if __name__ == "__main__":
    unittest.main()

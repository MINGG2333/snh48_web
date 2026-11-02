from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import Response

from website import fan_stats_api


class FanStatsApiTests(unittest.TestCase):
    def test_failed_platform_uses_last_successful_value_without_internal_error(self) -> None:
        last_success = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        latest = {
            "fetched_at": "2026-11-02 08:51:59",
            "platforms": {
                "weibo": {
                    "status": "error",
                    "label": "微博",
                    "error": "认证失败：primary: 微博 myblog 接口 返回 HTML 登录/验证页面，疑似 Cookie 已失效",
                },
                "bilibili": {
                    "status": "unsupported",
                    "label": "B站",
                    "error": "内部原因：账号池未配置",
                },
                "douyin": {
                    "status": "ok",
                    "label": "抖音",
                    "handle": "snh48陈嘉仪",
                    "followers": 11489,
                    "ts": "2026-11-02 08:51:59",
                    "source": "douyin_profile",
                },
            },
        }
        series = {
            "ts": last_success,
            "platform": "weibo",
            "handle": "SNH48-陈嘉仪",
            "followers": 3129,
            "source": "weibo_mymblog",
        }
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "latest.json").write_text(
                json.dumps(latest, ensure_ascii=False), encoding="utf-8"
            )
            Path(tmp, "fan_counts.jsonl").write_text(
                json.dumps(series, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            with patch.object(fan_stats_api.cfg, "FAN_COUNTS_DATA_PATH", tmp):
                result = fan_stats_api.get_fans_stats(Response(), days=30)

        payload = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("myblog", payload)
        self.assertNotIn("Cookie", payload)
        self.assertNotIn("账号池", payload)
        weibo = result["platforms"]["weibo"]
        self.assertEqual(weibo["status"], "error")
        self.assertEqual(weibo["followers"], 3129)
        self.assertEqual(weibo["ts"], last_success)
        self.assertTrue(weibo["stale"])
        self.assertNotIn("error", weibo)
        self.assertNotIn("error", result["platforms"]["bilibili"])
        self.assertEqual(result["platforms"]["douyin"]["followers"], 11489)
        self.assertEqual(result["platforms"]["douyin"]["source"], "douyin_profile")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Response

from website import fan_stats_api


class FanStatsApiTests(unittest.TestCase):
    def test_internal_errors_are_not_exposed(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "latest.json").write_text(
                json.dumps(latest, ensure_ascii=False), encoding="utf-8"
            )
            with patch.object(fan_stats_api.cfg, "FAN_COUNTS_DATA_PATH", tmp):
                result = fan_stats_api.get_fans_stats(Response(), days=30)

        payload = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("myblog", payload)
        self.assertNotIn("Cookie", payload)
        self.assertNotIn("账号池", payload)
        self.assertEqual(
            result["platforms"]["weibo"]["error"],
            fan_stats_api.PUBLIC_ERROR_TEXT["error"],
        )
        self.assertEqual(
            result["platforms"]["bilibili"]["error"],
            fan_stats_api.PUBLIC_ERROR_TEXT["unsupported"],
        )
        self.assertEqual(result["platforms"]["douyin"]["followers"], 11489)
        self.assertEqual(result["platforms"]["douyin"]["source"], "douyin_profile")


if __name__ == "__main__":
    unittest.main()

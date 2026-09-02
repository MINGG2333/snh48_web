from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from website import config as cfg
from website import maintenance
from website.complaint_api import router as complaint_router


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MaintenanceGuardTests(unittest.TestCase):
    def test_disabled_mode_allows_writes(self) -> None:
        with mock.patch.object(cfg, "SITE_MAINTENANCE_MODE", False):
            self.assertIsNone(maintenance.ensure_writable())

    def test_enabled_mode_returns_retryable_503(self) -> None:
        with (
            mock.patch.object(cfg, "SITE_MAINTENANCE_MODE", True),
            mock.patch.object(cfg, "SITE_MAINTENANCE_MESSAGE", "迁移中"),
            mock.patch.object(cfg, "SITE_MAINTENANCE_RETRY_AFTER_SECONDS", 123),
        ):
            with self.assertRaises(HTTPException) as raised:
                maintenance.ensure_writable()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "迁移中")
        self.assertEqual(raised.exception.headers["Retry-After"], "123")

    def test_business_write_endpoint_is_drained_before_storage(self) -> None:
        app = FastAPI()
        app.include_router(complaint_router)
        client = TestClient(app)
        with mock.patch.object(cfg, "SITE_MAINTENANCE_MODE", True):
            response = client.post(
                "/api/complaint/submit",
                json={
                    "type": "technical",
                    "content": "这是用于迁移维护模式回归测试的投诉内容。",
                    "captcha_challenge": "unknown-token",
                    "captcha_answer": "4821",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Retry-After"], str(cfg.SITE_MAINTENANCE_RETRY_AFTER_SECONDS))

    def test_node_label_can_be_overridden_without_changing_node_id(self) -> None:
        script = """
from website import config
assert config.SHARED_STATE_NODE_ID == "aliyun-new"
assert config.SHARED_STATE_NODE_LABELS["aliyun-new"] == "新公开站"
assert config.SHARED_STATE_NODE_LABELS["tencent"] == "腾讯旧站"
"""
        env = os.environ.copy()
        env["SHARED_STATE_NODE_ID"] = "aliyun-new"
        env["SHARED_STATE_NODE_LABEL"] = "新公开站"
        env["SHARED_STATE_NODE_LABELS_JSON"] = json.dumps(
            {"tencent": "腾讯旧站"}, ensure_ascii=False
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()

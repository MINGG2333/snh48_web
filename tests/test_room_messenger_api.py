from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from website import room_messenger_api as api


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


class RoomMessengerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = self.root / "member_catalog.json"
        self.catalog.write_text(
            json.dumps(
                {
                    "rooms": [
                        {
                            "channel_id": "1001",
                            "server_id": "2001",
                            "owner_id": "3001",
                            "owner_name": "陈嘉仪",
                            "group_name": "SNH48",
                            "in_group": True,
                            "room_type": "main",
                            "room_label": "公开房间",
                        },
                        {
                            "channel_id": "1002",
                            "server_id": "2002",
                            "owner_id": "3001",
                            "owner_name": "陈嘉仪",
                            "group_name": "SNH48",
                            "in_group": True,
                            "room_type": "small",
                            "room_label": "小房间",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.room_config = self.root / "room_monitor.json"
        self.room_config.write_text(
            json.dumps(
                {
                    "members": [
                        {
                            "id": "4001",
                            "name": "配置成员",
                            "channelId": "4002",
                            "serverId": "4003",
                            "rooms": [
                                {
                                    "type": "small",
                                    "label": "小房间",
                                    "channelId": "4004",
                                    "serverId": "4003",
                                }
                            ],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.patches = [
            patch.object(api.cfg, "ROOM_MESSENGER_ENABLED", True),
            patch.object(api.cfg, "ROOM_MESSENGER_PASSWORD", "correct-password"),
            patch.object(api.cfg, "SECURE_COOKIES", False),
            patch.object(api.cfg, "ROOM_MESSENGER_STATE_DIR", str(self.root / "state")),
            patch.object(api.cfg, "ROOM_MESSENGER_CATALOG_PATH", str(self.catalog)),
            patch.object(api.cfg, "ROOM_MESSENGER_ROOM_CONFIG_PATH", str(self.room_config)),
            patch.object(api.cfg, "ROOM_MESSENGER_DAILY_SEND_CAP", 10),
            patch.object(api.cfg, "ROOM_MESSENGER_MIN_INTERVAL_SECONDS", 15),
            patch.object(api.cfg, "ROOM_MESSENGER_DEFAULT_INTERVAL_SECONDS", 60),
            patch.object(api.cfg, "ROOM_MESSENGER_MAX_BATCH_MESSAGES", 30),
            patch.object(api.cfg, "ROOM_MESSENGER_MAX_JITTER_SECONDS", 120),
            patch.object(api.cfg, "ROOM_MESSENGER_CHUNK_SECONDS", 300),
        ]
        for item in self.patches:
            item.start()
        api._catalog_cache = None
        api._state_lock = api.threading.RLock()
        self.client = make_client()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _login(self):
        response = self.client.post(
            "/api/room-messenger/login", json={"password": "correct-password"}
        )
        self.assertEqual(response.status_code, 200)
        return response

    def _bind(self) -> None:
        api._set_binding("3001", "陈嘉仪")

    def test_stale_cookie_is_login_expired_not_rate_limited(self) -> None:
        for _ in range(12):
            response = self.client.get(
                "/api/room-messenger/account",
                headers={"Cookie": "room_messenger_auth=stale"},
            )
            self.assertEqual(response.status_code, 401)

    def test_login_and_verify_use_cookie_session(self) -> None:
        response = self.client.post(
            "/api/room-messenger/login", json={"password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 403)
        response = self._login()
        self.assertIn("HttpOnly", response.headers.get("set-cookie", ""))
        self.assertIn("Path=/api/room-messenger", response.headers.get("set-cookie", ""))
        self.assertEqual(self.client.get("/api/room-messenger/verify").status_code, 200)

    def test_catalog_groups_main_and_small_rooms(self) -> None:
        self._login()
        response = self.client.get("/api/room-messenger/catalog?q=陈嘉仪")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["members"][0]["rooms"]), 2)
        self.assertEqual(data["members"][0]["rooms"][0]["room_type"], "main")
        configured = self.client.get("/api/room-messenger/catalog?q=配置成员").json()
        self.assertEqual(configured["total"], 1)
        self.assertEqual(len(configured["members"][0]["rooms"]), 2)
        self.assertEqual(
            {room["channel_id"] for room in configured["members"][0]["rooms"]},
            {"4002", "4004"},
        )

    def test_manual_send_requires_exact_confirmation_word(self) -> None:
        self._login()
        self._bind()
        payload = {
            "channel_id": "1001",
            "server_id": "2001",
            "text": "hello",
            "confirm": "发送",
        }
        self.assertEqual(
            self.client.post("/api/room-messenger/send", json=payload, headers={"Origin": "http://testserver"}).status_code, 422
        )
        payload["confirm"] = api.SEND_CONFIRM_WORD
        with patch.object(
            api,
            "_run_bridge",
            return_value={"ok": True, "results": [{"ok": True, "msg_id_server": "9"}]},
        ) as bridge:
            response = self.client.post("/api/room-messenger/send", json=payload, headers={"Origin": "http://testserver"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["daily_sent"], 1)
        self.assertEqual(bridge.call_args.args[0], "messenger-send")

    def test_daily_cap_blocks_manual_send(self) -> None:
        self._login()
        self._bind()
        api._add_daily_sent("3001", 10)
        response = self.client.post(
            "/api/room-messenger/send",
            headers={"Origin": "http://testserver"},
            json={
                "channel_id": "1001",
                "server_id": "2001",
                "text": "hello",
                "confirm": api.SEND_CONFIRM_WORD,
            },
        )
        self.assertEqual(response.status_code, 429)

    def test_create_and_list_jobs(self) -> None:
        self._login()
        self._bind()
        response = self.client.post(
            "/api/room-messenger/jobs",
            headers={"Origin": "http://testserver"},
            json={
                "channel": {
                    "channel_id": "1001",
                    "server_id": "2001",
                    "member_name": "陈嘉仪",
                    "room_label": "公开房间",
                },
                "messages": ["第一条", "第二条"],
                "interval_seconds": 30,
                "jitter_seconds": 5,
                "start_at": "2099-01-01T20:00:00+08:00",
                "repeat_daily": False,
                "confirm": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()["job"]
        self.assertEqual(job["mode"], "batch")
        self.assertEqual(job["total"], 2)
        listed = self.client.get("/api/room-messenger/jobs").json()["jobs"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], job["id"])

    def test_job_creation_requires_confirmation(self) -> None:
        self._login()
        self._bind()
        response = self.client.post(
            "/api/room-messenger/jobs",
            headers={"Origin": "http://testserver"},
            json={
                "channel": {"channel_id": "1001", "server_id": "2001"},
                "messages": ["hello"],
                "start_at": "2099-01-01T20:00:00+08:00",
                "confirm": False,
            },
        )
        self.assertEqual(response.status_code, 422)


    def test_delete_requires_confirm_word_and_own_message(self) -> None:
        self._login()
        self._bind()
        payload = {
            "channel_id": "1001",
            "msg_id_client": "abc",
            "msg_time": 1700000000000,
            "sender_id": "3001",
            "confirm": "删除",
        }
        self.assertEqual(
            self.client.post(
                "/api/room-messenger/delete",
                headers={"Origin": "http://testserver"},
                json=payload,
            ).status_code,
            422,
        )
        payload["confirm"] = api.DELETE_CONFIRM_WORD
        payload["sender_id"] = "999"
        self.assertEqual(
            self.client.post(
                "/api/room-messenger/delete",
                headers={"Origin": "http://testserver"},
                json=payload,
            ).status_code,
            403,
        )
        payload["sender_id"] = "3001"
        with patch.object(api, "_run_bridge", return_value={"ok": True, "message": "OK"}) as bridge:
            result = self.client.post(
                "/api/room-messenger/delete",
                headers={"Origin": "http://testserver"},
                json=payload,
            )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(bridge.call_args.args[0], "messenger-delete")

    def test_switch_account_updates_binding(self) -> None:
        self._login()
        self._bind()
        with patch.object(
            api,
            "_run_bridge",
            return_value={
                "ok": True,
                "switched": True,
                "account": {"id": "174063630", "nickname": "小号"},
            },
        ) as bridge:
            result = self.client.post(
                "/api/room-messenger/account/switch",
                headers={"Origin": "http://testserver"},
                json={"target_user_id": "174063630"},
            )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["binding"]["account_id"], "174063630")
        self.assertEqual(bridge.call_args.args[0], "messenger-switch")


    def test_deleted_message_is_kept_as_tombstone_in_history(self) -> None:
        self._login()
        self._bind()
        api._record_deleted(
            "3001",
            "1001",
            {
                "msg_id_client": "abc",
                "msg_time": 1700000000000,
                "sender_id": "3001",
                "sender_name": "陈嘉仪",
                "text": "原始内容",
            },
        )
        with patch.object(api, "_run_bridge", return_value={"ok": True, "messages": [], "next_time": 0}):
            data = self.client.get(
                "/api/room-messenger/messages",
                params={"channel_id": "1001", "server_id": "2001", "next_time": 0},
            ).json()
        self.assertEqual(len(data["messages"]), 1)
        self.assertTrue(data["messages"][0]["deleted"])
        self.assertEqual(data["messages"][0]["text"], "原始内容")

    def test_delete_endpoint_records_tombstone_and_audit(self) -> None:
        self._login()
        self._bind()
        with patch.object(api, "_run_bridge", return_value={"ok": True, "message": "OK"}):
            response = self.client.post(
                "/api/room-messenger/delete",
                headers={"Origin": "http://testserver"},
                json={
                    "channel_id": "1001",
                    "msg_id_client": "abc",
                    "msg_time": 1700000000000,
                    "sender_id": "3001",
                    "sender_name": "陈嘉仪",
                    "text": "原始内容",
                    "confirm": api.DELETE_CONFIRM_WORD,
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        rows = api._deleted_rows("3001", "1001")
        self.assertEqual(rows["abc"]["text"], "原始内容")
        audit = (Path(self.root / "state") / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"kind":"delete"', audit)
        self.assertIn("原始内容", audit)



    def test_manual_send_logs_full_text_and_returns_it(self) -> None:
        self._login()
        self._bind()
        text = "这是一条超过四十个字符的完整测试消息，用来确认发送日志保存的是完整文本而不是预览。" * 2
        with patch.object(
            api,
            "_run_bridge",
            return_value={"ok": True, "results": [{"ok": True, "msg_id_server": "9"}]},
        ):
            response = self.client.post(
                "/api/room-messenger/send",
                headers={"Origin": "http://testserver"},
                json={
                    "channel_id": "1001",
                    "server_id": "2001",
                    "text": text,
                    "confirm": api.SEND_CONFIRM_WORD,
                    "channel": {"member_name": "陈嘉仪", "room_label": "公开房间"},
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        log = self.client.get("/api/room-messenger/sent-log").json()["entries"]
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["text"], text)
        self.assertEqual(log[0]["status"], "sent")
        self.assertEqual(log[0]["member_name"], "陈嘉仪")

    def test_job_send_logs_full_text(self) -> None:
        self._bind()
        job_id = "b" * 32
        text = "批量任务里的完整消息文本"
        api._save_jobs(
            {
                job_id: {
                    "id": job_id,
                    "account_id": "3001",
                    "channel": {
                        "channel_id": "1001",
                        "server_id": "2001",
                        "member_name": "陈嘉仪",
                        "room_label": "公开房间",
                    },
                    "mode": "once",
                    "repeat_daily": False,
                    "messages": [{"text": text, "status": "pending", "sent_at": "", "error": ""}],
                    "interval_seconds": 15,
                    "jitter_seconds": 0,
                    "next_run_at": 0,
                    "created_at": "2026-01-01T00:00:00+08:00",
                    "updated_at": "2026-01-01T00:00:00+08:00",
                    "status": "running",
                    "last_error": "",
                    "last_sent_at": 0,
                }
            }
        )
        with patch.object(api, "_run_bridge", return_value={"ok": True, "results": [{"ok": True}]}):
            api._run_job(job_id)
        entries = api._read_sent_log(10, "3001")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], text)
        self.assertEqual(entries[0]["source"], "job")
        self.assertEqual(entries[0]["status"], "sent")


    def test_chunk_size_respects_interval_and_daily_cap(self) -> None:
        self._bind()
        job = {"interval_seconds": 60}
        with patch.object(api, "_daily_sent", return_value=0):
            self.assertEqual(api._chunk_size(job, 30, "3001"), 5)
        with patch.object(api, "_daily_sent", return_value=9):
            self.assertEqual(api._chunk_size(job, 30, "3001"), 1)
        with patch.object(api, "_daily_sent", return_value=10):
            self.assertEqual(api._chunk_size(job, 30, "3001"), 0)

    def test_run_job_marks_each_message_sent_and_completes(self) -> None:
        self._bind()
        job_id = "a" * 32
        api._save_jobs(
            {
                job_id: {
                    "id": job_id,
                    "account_id": "3001",
                    "channel": {
                        "channel_id": "1001",
                        "server_id": "2001",
                        "member_name": "陈嘉仪",
                        "room_label": "公开房间",
                    },
                    "mode": "batch",
                    "repeat_daily": False,
                    "messages": [
                        {"text": "第一条", "status": "pending", "sent_at": "", "error": ""},
                        {"text": "第二条", "status": "pending", "sent_at": "", "error": ""},
                    ],
                    "interval_seconds": 15,
                    "jitter_seconds": 0,
                    "next_run_at": 0,
                    "created_at": "2026-01-01T00:00:00+08:00",
                    "updated_at": "2026-01-01T00:00:00+08:00",
                    "status": "running",
                    "last_error": "",
                    "last_sent_at": 0,
                }
            }
        )
        with patch.object(
            api,
            "_run_bridge",
            return_value={
                "ok": True,
                "results": [{"ok": True}, {"ok": True}],
            },
        ):
            api._run_job(job_id)
        job = api._load_jobs()[job_id]
        self.assertEqual(job["status"], "completed")
        self.assertEqual([item["status"] for item in job["messages"]], ["sent", "sent"])
        self.assertEqual(api._daily_sent("3001"), 2)



if __name__ == "__main__":
    unittest.main()

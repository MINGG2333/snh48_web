import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from website import config as cfg
from website import identity_index
from website import redblue_ledger_api as api
from website.redblue_export import _business_text
from website.redblue_ledger_api import _weidian_changed, _weidian_order_score, router


class RedblueLedgerApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="redblue-test-"))
        (self.tmp / "identity.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "generated_at": "2026-10-24 12:00:00",
                    "accounts": {
                        "1001": {"latest_name": "Alice", "names": {"Alice": {}}, "last_seen": "2026-10-24 10:00:00"},
                        "1002": {"latest_name": "Bob", "names": {"Bob": {}}, "last_seen": "2026-10-24 11:00:00"},
                    },
                    "nicknames": {
                        "Alice": {"ids": ["1001"], "ambiguous": False},
                        "Bob": {"ids": ["1002"], "ambiguous": False},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp / "score.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "room-1",
                            "source": "room",
                            "event_time": "2026-10-24 12:00:00",
                            "sender_name": "Alice",
                            "sender_id": "1001",
                            "total_score": 3,
                            "gift_name": "礼物",
                            "gift_count": 3,
                        },
                        {
                            "id": "live-1",
                            "source": "live",
                            "event_time": "2026-10-24 13:00:00",
                            "sender_name": "Nobody",
                            "sender_id": "",
                            "total_score": 1,
                            "gift_name": "礼物",
                            "gift_count": 1,
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp / "weidian.json").write_text(
            json.dumps(
                {
                    "orders": [
                        {
                            "order_id": "O1",
                            "item_id": "7879362063",
                            "item_name": "红蓝鸡腿",
                            "add_time": "2026-10-24 14:00:00",
                            "status": "待发货",
                            "buyer_name": "Alice",
                            "buyer_note": "",
                            "seller_note": "",
                            "quantity": 2,
                            "amount": "52.50",
                            "shipped": False,
                            "shipped_at": "",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._old = {
            "password": cfg.REDBLUE_LEDGER_PASSWORD,
            "data": cfg.REDBLUE_LEDGER_DATA_PATH,
            "identity": cfg.REDBLUE_IDENTITY_INDEX_PATH,
            "fallback": cfg.REDBLUE_IDENTITY_FALLBACK_PATHS,
            "score": cfg.REDBLUE_SCORE_DATA_PATH,
            "authority": cfg.REDBLUE_GIFT_AUTHORITY_PATH,
            "weidian": cfg.REDBLUE_WEIDIAN_ORDERS_PATH,
            "cookie_secret": cfg.REDBLUE_COOKIE_SECRET_PATH,
            "ai": cfg.REDBLUE_AI_QUEUE_DIR,
            "wd": cfg.REDBLUE_WEIDIAN_QUEUE_DIR,
            "sync": cfg.SHARED_STATE_SYNC_ENABLED,
            "primary": cfg.SHARED_STATE_IS_PRIMARY,
        }
        cfg.REDBLUE_LEDGER_PASSWORD = "testpass"
        cfg.REDBLUE_LEDGER_DATA_PATH = str(self.tmp / "ledger.json")
        cfg.REDBLUE_IDENTITY_INDEX_PATH = str(self.tmp / "identity.json")
        cfg.REDBLUE_IDENTITY_FALLBACK_PATHS = {}
        cfg.REDBLUE_SCORE_DATA_PATH = str(self.tmp / "score.json")
        cfg.REDBLUE_GIFT_AUTHORITY_PATH = str(self.tmp / "authority.json")
        cfg.REDBLUE_WEIDIAN_ORDERS_PATH = str(self.tmp / "weidian.json")
        cfg.REDBLUE_COOKIE_SECRET_PATH = str(self.tmp / "cookie_secret")
        cfg.REDBLUE_AI_QUEUE_DIR = str(self.tmp / "ai")
        cfg.REDBLUE_WEIDIAN_QUEUE_DIR = str(self.tmp / "wd")
        cfg.SHARED_STATE_SYNC_ENABLED = False
        cfg.SHARED_STATE_IS_PRIMARY = True
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app, base_url="https://testserver")
        self.headers = {"X-Redblue-Password": "testpass"}

    def tearDown(self):
        cfg.REDBLUE_LEDGER_PASSWORD = self._old["password"]
        cfg.REDBLUE_LEDGER_DATA_PATH = self._old["data"]
        cfg.REDBLUE_IDENTITY_INDEX_PATH = self._old["identity"]
        cfg.REDBLUE_IDENTITY_FALLBACK_PATHS = self._old["fallback"]
        cfg.REDBLUE_SCORE_DATA_PATH = self._old["score"]
        cfg.REDBLUE_GIFT_AUTHORITY_PATH = self._old["authority"]
        cfg.REDBLUE_WEIDIAN_ORDERS_PATH = self._old["weidian"]
        cfg.REDBLUE_COOKIE_SECRET_PATH = self._old["cookie_secret"]
        cfg.REDBLUE_AI_QUEUE_DIR = self._old["ai"]
        cfg.REDBLUE_WEIDIAN_QUEUE_DIR = self._old["wd"]
        cfg.SHARED_STATE_SYNC_ENABLED = self._old["sync"]
        cfg.SHARED_STATE_IS_PRIMARY = self._old["primary"]
        api._COOKIE_SECRET_CACHE = None
        identity_index.clear_cache()

    def test_login_cookie_authenticates_and_logout_clears(self):
        response = self.client.post("/api/redblue/login", json={"password": "testpass"})
        self.assertEqual(response.status_code, 200)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("redblue_ledger_auth=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertIn("Path=/api/redblue", cookie)
        self.assertIn("Secure", cookie)
        self.assertEqual(response.headers.get("cache-control"), "no-store")

        verify = self.client.get("/api/redblue/verify")
        self.assertEqual(verify.status_code, 200)
        self.assertEqual(verify.headers.get("cache-control"), "no-store")
        self.assertEqual(self.client.get("/api/redblue/data").status_code, 200)
        created = self.client.post(
            "/api/redblue/entries",
            json={"raw_name": "Alice", "score": 1},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(self.client.get("/api/redblue/export/summary.png").status_code, 200)

        logout = self.client.post("/api/redblue/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(logout.headers.get("cache-control"), "no-store")
        self.assertEqual(self.client.get("/api/redblue/data").status_code, 401)

    def test_login_rejects_wrong_password_without_cookie(self):
        response = self.client.post("/api/redblue/login", json={"password": "wrong"})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(response.headers.get("set-cookie"))
        self.assertEqual(self.client.get("/api/redblue/data").status_code, 401)

    def test_legacy_header_password_still_works(self):
        response = self.client.get("/api/redblue/verify", headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_manual_entry_resolution_and_warning(self):
        resolved = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Alice", "score": 1},
        ).json()["result"]
        self.assertFalse(resolved["warning"])
        self.assertEqual(resolved["fan_id"], "1001")

        missing = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Nobody", "score": 2},
        ).json()["result"]
        self.assertTrue(missing["warning"])

        fixed = self.client.patch(
            f"/api/redblue/entries/{missing['id']}",
            headers=self.headers,
            json={"raw_id": "1002"},
        ).json()["result"]
        self.assertFalse(fixed["warning"])
        self.assertEqual(fixed["fan_id"], "1002")

    def test_sync_room_live_and_weidian(self):
        room = self.client.post("/api/redblue/sync/room-live", headers=self.headers).json()["result"]
        self.assertEqual(room, {"created": 2, "updated": 0})
        job_id = "a" * 32
        result_dir = self.tmp / "wd" / "results"
        result_dir.mkdir(parents=True)
        (result_dir / f"{job_id}.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
        weidian = self.client.post(
            "/api/redblue/weidian/sync/apply",
            headers=self.headers,
            json={"job_id": job_id},
        ).json()["result"]
        self.assertEqual(weidian, {"created": 1, "updated": 0})
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        self.assertEqual(data["summary"]["entry_count"], 3)
        self.assertEqual(data["summary"]["total_score"], 6.0)

    def test_weidian_name_ignores_notes(self):
        (self.tmp / "weidian.json").write_text(
            json.dumps(
                {
                    "orders": [
                        {
                            "order_id": "O1",
                            "item_id": "7879362063",
                            "item_name": "红蓝鸡腿",
                            "add_time": "2026-10-24 14:00:00",
                            "status": "待发货",
                            "buyer_name": "Alice",
                            "buyer_note": "想要id合影业务谢谢",
                            "seller_note": "EVOL笙",
                            "quantity": 2,
                            "amount": "52.50",
                            "shipped": False,
                            "shipped_at": "",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        job_id = "c" * 32
        result_dir = self.tmp / "wd" / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / f"{job_id}.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
        self.client.post(
            "/api/redblue/weidian/sync/apply",
            headers=self.headers,
            json={"job_id": job_id},
        )
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        entry = next(item for item in data["entries"] if item["source"] == "weidian")
        self.assertEqual(entry["raw_name"], "Alice")
        self.assertEqual(entry["raw_id"], "")
        self.assertEqual(entry["weidian"]["buyer_note"], "想要id合影业务谢谢")
        self.assertEqual(entry["weidian"]["seller_note"], "EVOL笙")

    def test_weidian_main_name_uses_latest_pocket_nickname_dynamically(self):
        (self.tmp / "weidian.json").write_text(
            json.dumps(
                {
                    "orders": [
                        {
                            "order_id": "O6",
                            "item_id": "7879362063",
                            "item_name": "红蓝鸡腿",
                            "add_time": "2026-10-24 14:00:00",
                            "status": "待发货",
                            "buyer_name": "AliceOld",
                            "buyer_note": "",
                            "seller_note": "",
                            "quantity": 1,
                            "amount": "26.25",
                            "shipped": False,
                            "shipped_at": "",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        index = {
            "version": 1,
            "accounts": {
                "1001": {
                    "latest_name": "Alice",
                    "names": {"Alice": {}, "AliceOld": {}},
                    "last_seen": "2026-11-02 10:00:00",
                }
            },
            "nicknames": {
                "Alice": {"ids": ["1001"], "last_seen": "2026-11-02 10:00:00"},
                "AliceOld": {"ids": ["1001"], "last_seen": "2026-11-01 10:00:00"},
            },
        }
        (self.tmp / "identity.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        identity_index.clear_cache()
        job_id = "e" * 32
        result_dir = self.tmp / "wd" / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / f"{job_id}.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
        self.client.post(
            "/api/redblue/weidian/sync/apply",
            headers=self.headers,
            json={"job_id": job_id},
        )
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        entry = next(item for item in data["entries"] if item["source"] == "weidian")
        self.assertEqual(entry["raw_name"], "AliceOld")
        self.assertEqual(entry["fan_name"], "Alice")

        index["accounts"]["1001"]["latest_name"] = "AliceNew"
        index["accounts"]["1001"]["names"]["AliceNew"] = {}
        index["nicknames"]["AliceNew"] = {"ids": ["1001"], "last_seen": "2026-11-03 10:00:00"}
        (self.tmp / "identity.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        identity_index.clear_cache()
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        entry = next(item for item in data["entries"] if item["source"] == "weidian")
        self.assertEqual(entry["raw_name"], "AliceOld")
        self.assertEqual(entry["fan_name"], "AliceNew")

    def test_weidian_rename_updates_scoring_name_not_current_nickname(self):
        (self.tmp / "weidian.json").write_text(
            json.dumps(
                {
                    "orders": [
                        {
                            "order_id": "O7",
                            "item_id": "7879362063",
                            "item_name": "红蓝鸡腿",
                            "add_time": "2026-10-24 14:00:00",
                            "status": "待发货",
                            "buyer_name": "AliceOld",
                            "buyer_note": "",
                            "seller_note": "",
                            "quantity": 1,
                            "amount": "26.25",
                            "shipped": False,
                            "shipped_at": "",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        index = {
            "version": 1,
            "accounts": {
                "1001": {
                    "latest_name": "Alice",
                    "names": {"Alice": {}, "AliceOld": {}, "AliceNew": {}},
                    "last_seen": "2026-11-02 10:00:00",
                }
            },
            "nicknames": {
                "Alice": {"ids": ["1001"], "last_seen": "2026-11-02 10:00:00"},
                "AliceOld": {"ids": ["1001"], "last_seen": "2026-11-01 10:00:00"},
                "AliceNew": {"ids": ["1001"], "last_seen": "2026-11-01 11:00:00"},
            },
        }
        (self.tmp / "identity.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        identity_index.clear_cache()
        job_id = "f" * 32
        result_dir = self.tmp / "wd" / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / f"{job_id}.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
        self.client.post(
            "/api/redblue/weidian/sync/apply",
            headers=self.headers,
            json={"job_id": job_id},
        )
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        entry = next(item for item in data["entries"] if item["source"] == "weidian")
        self.assertEqual(entry["raw_name"], "AliceOld")
        self.assertEqual(entry["fan_name"], "Alice")

        api.execute_mutation(
            api.RESOURCE,
            "rename_weidian",
            {"order_id": "O7", "name": "AliceNew"},
        )
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        entry = next(item for item in data["entries"] if item["source"] == "weidian")
        self.assertEqual(entry["raw_name"], "AliceNew")
        self.assertEqual(entry["fan_name"], "Alice")
        self.assertEqual(entry["weidian"]["buyer_name"], "AliceNew")
        fan = next(item for item in data["fan_summary"] if item["fan_name"] == "Alice")
        self.assertIn("AliceNew", fan["score_names"])
        self.assertEqual(fan["score_name"], "AliceNew")

    def test_weidian_note_can_supply_id_but_not_name(self):
        (self.tmp / "weidian.json").write_text(
            json.dumps(
                {
                    "orders": [
                        {
                            "order_id": "O5",
                            "item_id": "7879362063",
                            "item_name": "红蓝鸡腿",
                            "add_time": "2026-10-24 14:00:00",
                            "status": "待发货",
                            "buyer_name": "Alice",
                            "buyer_note": "口袋ID 133038462",
                            "seller_note": "",
                            "quantity": 1,
                            "amount": "26.25",
                            "shipped": False,
                            "shipped_at": "",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        job_id = "d" * 32
        result_dir = self.tmp / "wd" / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / f"{job_id}.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
        self.client.post(
            "/api/redblue/weidian/sync/apply",
            headers=self.headers,
            json={"job_id": job_id},
        )
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        entry = next(item for item in data["entries"] if item["source"] == "weidian")
        self.assertEqual(entry["raw_name"], "Alice")
        self.assertEqual(entry["raw_id"], "133038462")

    def test_scoring_method_is_derived_from_source(self):
        self.client.post("/api/redblue/sync/room-live", headers=self.headers)
        job_id = "b" * 32
        result_dir = self.tmp / "wd" / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / f"{job_id}.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
        self.client.post(
            "/api/redblue/weidian/sync/apply",
            headers=self.headers,
            json={"job_id": job_id},
        )
        manual = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Alice", "score": 1},
        ).json()["result"]
        self.assertEqual(manual["scoring_method"], "计分卡")
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        methods = {item["source"]: item["scoring_method"] for item in data["entries"]}
        self.assertEqual(methods["room"], "计分卡")
        self.assertEqual(methods["live"], "计分卡")
        self.assertEqual(methods["weidian"], "鸡腿")
        labels = {item["source"]: item["source_scoring_label"] for item in data["entries"]}
        self.assertEqual(labels["room"], "房间·计分卡")
        self.assertEqual(labels["live"], "直播·计分卡")
        self.assertEqual(labels["weidian"], "应援会·鸡腿")
        self.assertEqual(labels["manual"], "暗票·计分卡")

    def test_daily_scoring_fills_days_from_start(self):
        self.client.post("/api/redblue/sync/room-live", headers=self.headers)
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        daily = data["daily_scoring"]
        self.assertEqual(daily["start"], "2026-10-24")
        self.assertEqual(
            [item["key"] for item in daily["categories"]],
            ["room|计分卡", "room|鸡腿", "live|计分卡", "live|鸡腿", "weidian|鸡腿", "manual|计分卡"],
        )
        first = daily["days"][0]
        self.assertEqual(first["date"], "2026-10-24")
        self.assertEqual(first["scores"]["room|计分卡"], 3.0)
        self.assertEqual(first["scores"]["live|计分卡"], 1.0)
        self.assertEqual(first["total"], 4.0)
        self.assertEqual(first["count"], 2)
        expected_days = (date.fromisoformat(daily["end"]) - date.fromisoformat(daily["start"])).days + 1
        self.assertEqual(len(daily["days"]), expected_days)
        self.assertEqual(daily["total_score"], data["overall"]["total_score"])

    def test_chicken_gift_is_marked_as_chicken_leg(self):
        (self.tmp / "score.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "room-card",
                            "source": "room",
                            "event_time": "2026-11-11 12:00:00",
                            "sender_name": "Alice",
                            "sender_id": "1001",
                            "total_score": 1,
                            "gift_name": "弦月回响",
                            "gift_count": 1,
                        },
                        {
                            "id": "room-leg",
                            "source": "room",
                            "event_time": "2026-11-11 12:01:00",
                            "sender_name": "Alice",
                            "sender_id": "1001",
                            "total_score": 5,
                            "gift_name": "红蓝1分鸡腿礼物",
                            "gift_count": 1,
                        },
                        {
                            "id": "live-leg",
                            "source": "live",
                            "event_time": "2026-11-11 12:02:00",
                            "sender_name": "Bob",
                            "sender_id": "1002",
                            "total_score": 2,
                            "gift_name": "红蓝1分鸡腿礼物",
                            "gift_count": 1,
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.client.post("/api/redblue/sync/room-live", headers=self.headers)
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        methods = {item["source_id"]: item["scoring_method"] for item in data["entries"]}
        self.assertEqual(methods["room-card"], "计分卡")
        self.assertEqual(methods["room-leg"], "鸡腿")
        self.assertEqual(methods["live-leg"], "鸡腿")
        fans = {fan["fan_name"]: fan for fan in data["fan_summary"]}
        self.assertEqual(fans["Alice"]["scoring"], {"计分卡": 1.0, "鸡腿": 5.0})
        self.assertEqual(fans["Bob"]["scoring"], {"鸡腿": 2.0})

    def test_chicken_gift_with_positive_price_is_marked_as_chicken_leg(self):
        (self.tmp / "authority.json").write_text(
            json.dumps(
                {
                    "gifts": [
                        {"gift_id": "350001", "gift_name": "红蓝应援礼物", "melee": 350.0, "money": 350.0},
                        {"gift_id": "1320115721784332288", "gift_name": "弦月回响", "melee": 350.0, "money": 350.0},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp / "score.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "room-price-leg",
                            "source": "room",
                            "event_time": "2026-11-11 12:00:00",
                            "sender_name": "Alice",
                            "sender_id": "1001",
                            "gift_id": "350001",
                            "gift_name": "红蓝应援礼物",
                            "gift_count": 1,
                            "total_score": 7,
                        },
                        {
                            "id": "room-card",
                            "source": "room",
                            "event_time": "2026-11-11 12:01:00",
                            "sender_name": "Alice",
                            "sender_id": "1001",
                            "gift_id": "1320115721784332288",
                            "gift_name": "弦月回响",
                            "gift_count": 1,
                            "total_score": 1,
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.client.post("/api/redblue/sync/room-live", headers=self.headers)
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        methods = {item["source_id"]: item["scoring_method"] for item in data["entries"]}
        self.assertEqual(methods["room-price-leg"], "鸡腿")
        self.assertEqual(methods["room-card"], "计分卡")

    def test_explicit_chicken_gift_name_is_supported(self):
        old = cfg.REDBLUE_CHICKEN_GIFT_NAMES
        cfg.REDBLUE_CHICKEN_GIFT_NAMES = "特别应援礼物"
        try:
            (self.tmp / "score.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "room-special",
                                "source": "room",
                                "event_time": "2026-12-02 12:00:00",
                                "sender_name": "Alice",
                                "sender_id": "1001",
                                "total_score": 3,
                                "gift_name": "特别应援礼物",
                                "gift_count": 1,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.client.post("/api/redblue/sync/room-live", headers=self.headers)
            data = self.client.get("/api/redblue/data", headers=self.headers).json()
            self.assertEqual(data["entries"][0]["scoring_method"], "鸡腿")
        finally:
            cfg.REDBLUE_CHICKEN_GIFT_NAMES = old

    def test_explicit_chicken_gift_id_is_supported(self):
        old = cfg.REDBLUE_CHICKEN_GIFT_IDS
        cfg.REDBLUE_CHICKEN_GIFT_IDS = "999888"
        try:
            (self.tmp / "score.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "room-by-id",
                                "source": "room",
                                "event_time": "2026-12-03 12:00:00",
                                "sender_name": "Alice",
                                "sender_id": "1001",
                                "total_score": 4,
                                "gift_id": "999888",
                                "gift_name": "特别应援",
                                "gift_count": 1,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.client.post("/api/redblue/sync/room-live", headers=self.headers)
            data = self.client.get("/api/redblue/data", headers=self.headers).json()
            self.assertEqual(data["entries"][0]["scoring_method"], "鸡腿")
        finally:
            cfg.REDBLUE_CHICKEN_GIFT_IDS = old

    def test_weidian_score_uses_amount_or_explicit_score(self):
        order = {"order_id": "O2", "item_id": "7879362063", "quantity": 1, "amount": "2598.75"}
        self.assertEqual(_weidian_order_score(order), 99.0)
        self.assertEqual(_weidian_order_score({**order, "score": 99}), 99.0)
        self.assertEqual(_weidian_order_score({**order, "amount": "26.25"}), 1.0)
        self.assertEqual(_weidian_order_score({"order_id": "O3", "quantity": 5}), 5.0)

    def test_weidian_score_change_is_detected(self):
        doc = {
            "entries": [
                {
                    "source": "weidian",
                    "source_id": "O2",
                    "score": 1.0,
                    "settled": False,
                    "weidian": {
                        "order_id": "O2",
                        "item_id": "7879362063",
                        "item_name": "红蓝鸡腿",
                        "status": "待发货",
                        "buyer_name": "Alice",
                        "buyer_note": "",
                        "seller_note": "",
                        "quantity": 1,
                    },
                }
            ]
        }
        order = {
            "order_id": "O2",
            "item_id": "7879362063",
            "item_name": "红蓝鸡腿",
            "status": "待发货",
            "buyer_name": "Alice",
            "buyer_note": "",
            "seller_note": "",
            "quantity": 1,
            "amount": "2598.75",
            "shipped": False,
        }
        self.assertTrue(_weidian_changed(doc, [order]))
        doc["entries"][0]["score"] = 99.0
        self.assertFalse(_weidian_changed(doc, [order]))

    def test_weidian_item_name_change_is_detected(self):
        doc = {
            "entries": [
                {
                    "source": "weidian",
                    "source_id": "O1",
                    "score": 2.0,
                    "settled": False,
                    "weidian": {
                        "order_id": "O1",
                        "item_id": "7879362063",
                        "item_name": "旧商品名",
                        "status": "待发货",
                        "buyer_name": "Alice",
                        "buyer_note": "",
                        "seller_note": "",
                        "quantity": 2,
                    },
                }
            ]
        }
        order = {
            "order_id": "O1",
            "item_id": "7879362063",
            "item_name": "新商品名",
            "status": "待发货",
            "buyer_name": "Alice",
            "buyer_note": "",
            "seller_note": "",
            "quantity": 2,
            "shipped": False,
        }
        self.assertTrue(_weidian_changed(doc, [order]))
        doc["entries"][0]["weidian"]["item_name"] = "新商品名"
        self.assertFalse(_weidian_changed(doc, [order]))

    def test_weidian_sku_title_change_is_detected(self):
        doc = {
            "entries": [
                {
                    "source": "weidian",
                    "source_id": "O4",
                    "score": 1.0,
                    "settled": False,
                    "weidian": {
                        "order_id": "O4",
                        "item_id": "7879362063",
                        "item_name": "红蓝鸡腿",
                        "sku_title": "1份",
                        "quantity": 1,
                        "status": "待发货",
                        "buyer_name": "Alice",
                        "buyer_note": "",
                        "seller_note": "",
                    },
                }
            ]
        }
        order = {
            "order_id": "O4",
            "item_id": "7879362063",
            "item_name": "红蓝鸡腿",
            "sku_title": "99份",
            "quantity": 1,
            "status": "待发货",
            "buyer_name": "Alice",
            "buyer_note": "",
            "seller_note": "",
            "shipped": False,
        }
        self.assertTrue(_weidian_changed(doc, [order]))
        doc["entries"][0]["weidian"]["sku_title"] = "99份"
        self.assertFalse(_weidian_changed(doc, [order]))

    def test_duplicate_is_excluded_from_summary(self):
        cfg.REDBLUE_SCORE_DATA_PATH = str(self.tmp / "missing.json")
        entry = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Alice", "score": 4},
        ).json()["result"]
        self.client.post(
            f"/api/redblue/entries/{entry['id']}/duplicate",
            headers=self.headers,
            json={"duplicate": True},
        )
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        self.assertEqual(data["summary"]["entry_count"], 0)
        self.assertEqual(data["summary"]["duplicate_count"], 1)

    def test_fan_summary_keeps_scoring_name_alias(self):
        self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "AliceOld", "raw_id": "1001", "score": 2},
        )
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        fan = next(item for item in data["fan_summary"] if item["fan_name"] == "Alice")
        self.assertIn("AliceOld", fan["score_names"])
        self.assertEqual(fan["score_name"], "AliceOld")

    def test_fan_summary_ties_follow_reached_time(self):
        fans = api._fan_summary(
            [
                {
                    "fan_id": "1",
                    "fan_name": "Later",
                    "score": 1,
                    "settled": True,
                    "source_time": "2026-10-24 09:00:00",
                },
                {
                    "fan_id": "1",
                    "fan_name": "Later",
                    "score": 1,
                    "settled": True,
                    "source_time": "2026-10-24 12:00:00",
                },
                {
                    "fan_id": "2",
                    "fan_name": "Earlier",
                    "score": 2,
                    "settled": True,
                    "source_time": "2026-10-24 10:00:00",
                },
            ]
        )
        self.assertEqual([fan["fan_name"] for fan in fans], ["Earlier", "Later"])
        self.assertEqual(fans[0]["reached_at"], "2026-10-24 10:00:00")
        self.assertEqual(fans[1]["reached_at"], "2026-10-24 12:00:00")

    def test_business_done_toggle(self):
        entry = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Alice", "score": 1},
        ).json()["result"]
        patched = self.client.patch(
            f"/api/redblue/entries/{entry['id']}",
            headers=self.headers,
            json={"business_done": True},
        ).json()["result"]
        self.assertTrue(patched["business_done"])
        self.assertTrue(patched["business_done_at"])
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        row = next(item for item in data["entries"] if item["id"] == entry["id"])
        self.assertTrue(row["business_done"])

    def test_business_options_use_score_prefix_from_chart(self):
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        options = data["business_options"]
        values = {item["value"] for item in options}
        self.assertIn("1-方言盲盒", values)
        self.assertIn("6-点唱整首", values)
        self.assertIn("9-答案之书", values)
        self.assertIn("99-跳公演", values)
        self.assertEqual(len(values), len(options))
        card = next(item for item in options if item["value"] == "1-方言盲盒")
        self.assertEqual(card["score"], 1)
        self.assertEqual(card["name"], "方言盲盒")

    def test_selected_business_is_saved_and_validated(self):
        entry = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Alice", "score": 6, "selected_business": "6-点唱整首"},
        ).json()["result"]
        self.assertEqual(entry["selected_business"], "6-点唱整首")
        patched = self.client.patch(
            f"/api/redblue/entries/{entry['id']}",
            headers=self.headers,
            json={"selected_business": "9-歌词卡"},
        ).json()["result"]
        self.assertEqual(patched["selected_business"], "9-歌词卡")
        cleared = self.client.patch(
            f"/api/redblue/entries/{entry['id']}",
            headers=self.headers,
            json={"selected_business": "不存在-业务"},
        ).json()["result"]
        self.assertEqual(cleared["selected_business"], "")
        bonus = self.client.patch(
            f"/api/redblue/entries/{entry['id']}",
            headers=self.headers,
            json={"selected_business_bonus": "9-答案之书"},
        ).json()["result"]
        self.assertEqual(bonus["selected_business_bonus"], "9-答案之书")
        bad_bonus = self.client.patch(
            f"/api/redblue/entries/{entry['id']}",
            headers=self.headers,
            json={"selected_business_bonus": "6-点唱整首"},
        ).json()["result"]
        self.assertEqual(bad_bonus["selected_business_bonus"], "")
        data = self.client.get("/api/redblue/data", headers=self.headers).json()
        row = next(item for item in data["entries"] if item["id"] == entry["id"])
        self.assertEqual(row["selected_business"], "")
        self.assertEqual(row["selected_business_bonus"], "")

    def test_export_business_text_uses_names_only(self):
        self.assertEqual(_business_text({"selected_business": "6-ID 合影"}), "ID 合影")
        self.assertEqual(
            _business_text(
                {
                    "selected_business": "6-ID 合影",
                    "selected_business_bonus": "18-点唱整首",
                }
            ),
            "ID 合影+点唱整首",
        )
        self.assertEqual(
            _business_text(
                {
                    "selected_business": "9-答案之书",
                    "selected_business_bonus": "9-答案之书",
                }
            ),
            "答案之书",
        )
        self.assertEqual(_business_text({}), "")

    def test_cookie_secret_persists_across_reloads(self):
        api._COOKIE_SECRET_CACHE = None
        first = api._cookie_secret()
        api._COOKIE_SECRET_CACHE = None
        second = api._cookie_secret()
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 16)
        path = Path(cfg.REDBLUE_COOKIE_SECRET_PATH)
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_two_image_exports(self):
        import io

        from PIL import Image

        self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Alice", "score": 1},
        )
        images = {}
        for name in ("summary", "entries"):
            response = self.client.get(f"/api/redblue/export/{name}.png", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/png")
            self.assertTrue(response.content.startswith(b"\x89PNG"))
            images[name] = Image.open(io.BytesIO(response.content))
        self.assertLess(images["summary"].size[0], 1000)
        self.assertGreater(images["summary"].size[0], 500)
        self.assertEqual(images["entries"].size[0], 820)

    def test_entries_export_expands_for_full_business_name(self):
        import io

        from PIL import Image

        entry = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={
                "raw_name": "Alice",
                "score": 18,
                "selected_business": "18-换口袋头像或背景两天",
            },
        ).json()["result"]
        self.client.patch(
            f"/api/redblue/entries/{entry['id']}",
            headers=self.headers,
            json={"selected_business_bonus": "48-公演 MC 指定动作"},
        )
        response = self.client.get("/api/redblue/export/entries.png", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        image = Image.open(io.BytesIO(response.content))
        self.assertGreater(image.size[0], 820)

    def test_entries_export_expands_for_full_fan_name(self):
        import io

        from PIL import Image

        self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "很长很长很长很长很长很长很长的粉丝昵称", "score": 1},
        )
        response = self.client.get("/api/redblue/export/entries.png", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        image = Image.open(io.BytesIO(response.content))
        self.assertGreater(image.size[0], 820)

    def test_ai_job_is_queued_and_apply_validates_identity(self):
        entry = self.client.post(
            "/api/redblue/entries",
            headers=self.headers,
            json={"raw_name": "Nobody", "score": 1},
        ).json()["result"]
        job = self.client.post("/api/redblue/ai/jobs", headers=self.headers, json={}).json()
        self.assertEqual(job["count"], 1)
        pending = self.tmp / "ai" / "pending" / f"{job['job_id']}.json"
        self.assertTrue(pending.exists())
        # Simulate a worker result and apply it.
        results = self.tmp / "ai" / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / f"{job['job_id']}.json").write_text(
            json.dumps(
                {
                    "status": "done",
                    "backend": "codex",
                    "suggestions": [
                        {
                            "entry_id": entry["id"],
                            "fan_id": "1002",
                            "fan_name": "Bob",
                            "confidence": 0.9,
                            "reason": "test",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        applied = self.client.post(
            f"/api/redblue/ai/jobs/{job['job_id']}/apply",
            headers=self.headers,
        ).json()["result"]
        self.assertEqual(applied, {"applied": 1, "skipped": 0})


if __name__ == "__main__":
    unittest.main()

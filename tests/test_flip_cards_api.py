from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from website.flip_cards_api import router


class FlipCardsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / "flip_data"
        self.dataset_path = self.data_dir / "web" / "flip_cards.json"
        (self.data_dir / "web").mkdir(parents=True)
        (self.data_dir / "audio").mkdir()
        (self.data_dir / "audio" / "voice.mp3").write_bytes(b"0123456789")
        self.dataset_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "member": "测试成员",
                    "member_avatar_text": "嘉仪",
                    "summary": {"total": 1, "answered": 1},
                    "records": [
                        {
                            "question_id": "q1",
                            "status": "answered",
                            "answer_type": "audio",
                            "qtime_text": "2026-07-20 20:00",
                            "content": "问题",
                            "audio_transcript": {"text": "这是语音转录"},
                            "media": {
                                "kind": "audio",
                                "filename": "voice.mp3",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        app = FastAPI()
        app.include_router(router)
        self.patches = [
            mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_PASSWORD", "test-password"),
            mock.patch("website.flip_cards_api.cfg.SECURE_COOKIES", False),
            mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_DATASET_PATH", str(self.dataset_path)),
            mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_DATA_DIR", str(self.data_dir)),
            mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_ACCOUNTS_PATH", str(self.data_dir / "web" / "accounts.json")),
            mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED", False),
        ]
        for patcher in self.patches:
            patcher.start()
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    async def test_login_unlocks_application_data_and_media(self) -> None:
        self.assertEqual((await self.client.get("/api/flip-cards/data")).status_code, 401)
        login = await self.client.post("/api/flip-cards/login", json={"password": "test-password"})
        self.assertEqual(login.status_code, 200)

        status = await self.client.get("/api/flip-cards/status")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["dataset_exists"])
        self.assertTrue(status.json()["dataset_version"])

        data = await self.client.get("/api/flip-cards/data")
        self.assertEqual(data.status_code, 200)
        record = data.json()["records"][0]
        self.assertEqual(record["qtime_text"], "2026-07-20 20:00")
        self.assertEqual(record["audio_transcript"]["text"], "这是语音转录")
        self.assertEqual(record["media"]["url"], "/api/flip-cards/flip_data/audio/voice.mp3")

        media = await self.client.get(
            "/api/flip-cards/flip_data/audio/voice.mp3",
            headers={"Range": "bytes=2-5"},
        )
        self.assertEqual(media.status_code, 206)
        self.assertEqual(media.content, b"2345")
        self.assertEqual(media.headers["content-range"], "bytes 2-5/10")

        html = await self.client.get("/api/flip-cards/html")
        self.assertEqual(html.status_code, 404)

    async def test_selects_account_scoped_dataset_and_media_from_manifest(self) -> None:
        account_id = "172884074"
        (self.data_dir / "web" / "accounts").mkdir()
        (self.data_dir / "audio" / account_id).mkdir()
        (self.data_dir / "audio" / account_id / "scoped.mp3").write_bytes(b"account-audio")
        (self.data_dir / "web" / "accounts.json").write_text(
            json.dumps({
                "schema_version": 1,
                "default_account_id": account_id,
                "accounts": [{"id": account_id, "nickname": "xxgg2333"}],
            }),
            encoding="utf-8",
        )
        (self.data_dir / "web" / "accounts" / f"{account_id}.json").write_text(
            json.dumps({
                "schema_version": 3,
                "account": {"id": account_id, "nickname": "xxgg2333"},
                "summary": {"total": 1},
                "records": [{"question_id": "q2", "media": {"kind": "audio", "filename": "scoped.mp3"}}],
            }),
            encoding="utf-8",
        )
        await self.client.post("/api/flip-cards/login", json={"password": "test-password"})

        accounts = await self.client.get("/api/flip-cards/accounts")
        self.assertEqual(accounts.json()["accounts"][0]["nickname"], "xxgg2333")
        data = await self.client.get(f"/api/flip-cards/data?account_id={account_id}")
        self.assertEqual(data.json()["account"]["id"], account_id)
        self.assertEqual(
            data.json()["records"][0]["media"]["url"],
            f"/api/flip-cards/accounts/{account_id}/flip_data/audio/scoped.mp3",
        )
        media = await self.client.get(f"/api/flip-cards/accounts/{account_id}/flip_data/audio/scoped.mp3")
        self.assertEqual(media.content, b"account-audio")
        missing = await self.client.get("/api/flip-cards/data?account_id=999999")
        self.assertEqual(missing.status_code, 404)

        status = await self.client.get(f"/api/flip-cards/status?account_id={account_id}")
        self.assertEqual(status.json()["account_id"], account_id)
        self.assertTrue(status.json()["dataset_version"])

    async def test_account_management_is_disabled_on_non_primary_node(self) -> None:
        await self.client.post("/api/flip-cards/login", json={"password": "test-password"})
        capability = await self.client.get("/api/flip-cards/account-management/status")
        self.assertFalse(capability.json()["enabled"])
        response = await self.client.post(
            "/api/flip-cards/account-management/send-sms",
            json={"phone": "13800001234", "area": "86"},
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(response.status_code, 403)
        latest = await self.client.get(
            "/api/flip-cards/account-management/latest-job?account_id=172884074"
        )
        self.assertEqual(latest.status_code, 403)

    async def test_account_management_requires_same_origin(self) -> None:
        await self.client.post("/api/flip-cards/login", json={"password": "test-password"})
        with mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED", True):
            response = await self.client.post(
                "/api/flip-cards/account-management/send-sms",
                json={"phone": "13800001234", "area": "86"},
                headers={"Origin": "https://evil.example"},
            )
        self.assertEqual(response.status_code, 403)

    async def test_latest_job_uses_safe_account_id_and_admin_bridge(self) -> None:
        await self.client.post("/api/flip-cards/login", json={"password": "test-password"})
        with (
            mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED", True),
            mock.patch(
                "website.flip_cards_api._run_account_admin",
                return_value={"ok": True, "job": {"job_id": "a" * 32, "state": "running"}},
            ) as run_admin,
        ):
            response = await self.client.get(
                "/api/flip-cards/account-management/latest-job?account_id=172884074"
            )

        self.assertEqual(response.status_code, 200)
        run_admin.assert_called_once_with("latest-job", {"account_id": "172884074"})


class FlipCardsTemplateTests(unittest.TestCase):
    def test_template_renders_application_instead_of_redirecting_to_html(self) -> None:
        template = Path("website/templates/flip_cards.html").read_text(encoding="utf-8")
        self.assertIn('const API = "/api/flip-cards"', template)
        self.assertIn('apiJson("/data" + suffix)', template)
        self.assertIn('id="accountSelect"', template)
        self.assertIn('id="memberFilter"', template)
        self.assertIn('id="accountModal"', template)
        self.assertIn('id="updateModal"', template)
        self.assertIn('id="updateModalMinimize"', template)
        self.assertIn('aria-label="收起更新状态"', template)
        self.assertIn('id="updatePill"', template)
        self.assertNotIn('id="latestBtn"', template)
        self.assertIn('apiJson("/account-management/status")', template)
        self.assertIn('"/account-management/latest-job?account_id="', template)
        self.assertIn('"/account-management/send-sms"', template)
        self.assertIn('"/account-management/verify-code"', template)
        self.assertNotIn("前往腾讯云", template)
        self.assertIn("我发于 ", template)
        self.assertIn('const avatarText = memberAvatarText(record)', template)
        self.assertIn('avatar.textContent = avatarText', template)
        self.assertIn('record.member_avatar_text', template)
        self.assertIn('String(member.name || "").includes("陈嘉仪")', template)
        self.assertIn('createAudioTranscriptNode(record.audio_transcript)', template)
        self.assertIn('appendText(box, "transcript-label", "转录参考")', template)
        self.assertIn('<details id="filterPanel" class="filter-panel">', template)
        self.assertNotIn('<details id="filterPanel" class="filter-panel" open>', template)
        self.assertIn('filterPanel.addEventListener("toggle"', template)
        self.assertIn('action: "toggle_filters"', template)
        self.assertIn('datasetUpdateTimer = window.setInterval(checkDatasetUpdates, 15000)', template)
        self.assertIn('await loadSelectedAccount(true, true)', template)
        self.assertIn('"有新记录，点击查看最新"', template)
        self.assertIn('updatePill.addEventListener("click", loadLatestRecords)', template)
        self.assertIn('addQuestionStatus(meta, record)', template)
        self.assertIn('statusButton.dataset.target = "answer-" + safeId(record.question_id)', template)
        self.assertIn('statusButton.textContent = "已回复 · 查看回复"', template)
        self.assertIn('event.target.closest(".quote, .status-link")', template)
        self.assertIn('jumpsToAnswer ? "jump_to_flip_answer" : "jump_to_flip_question"', template)
        self.assertIn('}, 4000);', template)
        self.assertIn('outline: 3px solid #ffd666', template)
        self.assertNotIn('events.push({ type: "status"', template)
        self.assertNotIn('function createStatus(event)', template)
        self.assertNotIn('window.location.replace(API + "/html")', template)
        self.assertNotIn("/api/flip-cards/html", template)
        self.assertNotIn("downloadHtmlLink", template)
        for action in (
            "filter_status",
            "filter_member",
            "filter_answer_type",
            "toggle_filters",
            "reset_filters",
            "load_latest",
            "open_official_media",
            "jump_to_flip_question",
            "jump_to_flip_answer",
            "flip_media_play",
            "flip_media_pause",
            "flip_media_seek",
            "flip_media_complete",
        ):
            self.assertIn(action, template)


if __name__ == "__main__":
    unittest.main()

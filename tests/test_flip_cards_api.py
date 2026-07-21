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
                    "schema_version": 1,
                    "member": "测试成员",
                    "summary": {"total": 1, "answered": 1},
                    "records": [
                        {
                            "question_id": "q1",
                            "status": "answered",
                            "answer_type": "audio",
                            "qtime_text": "2026-07-20 20:00",
                            "content": "问题",
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
            mock.patch("website.flip_cards_api.cfg.FLIP_CARDS_HTML_PATH", str(self.root / "flip_chat.html")),
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

        data = await self.client.get("/api/flip-cards/data")
        self.assertEqual(data.status_code, 200)
        record = data.json()["records"][0]
        self.assertEqual(record["qtime_text"], "2026-07-20 20:00")
        self.assertEqual(record["media"]["url"], "/api/flip-cards/flip_data/audio/voice.mp3")

        media = await self.client.get(
            "/api/flip-cards/flip_data/audio/voice.mp3",
            headers={"Range": "bytes=2-5"},
        )
        self.assertEqual(media.status_code, 206)
        self.assertEqual(media.content, b"2345")
        self.assertEqual(media.headers["content-range"], "bytes 2-5/10")


class FlipCardsTemplateTests(unittest.TestCase):
    def test_template_renders_application_instead_of_redirecting_to_html(self) -> None:
        template = Path("website/templates/flip_cards.html").read_text(encoding="utf-8")
        self.assertIn('const API = "/api/flip-cards"', template)
        self.assertIn('apiJson("/data")', template)
        self.assertIn("我发于 ", template)
        self.assertNotIn('window.location.replace(API + "/html")', template)
        for action in (
            "filter_status",
            "filter_answer_type",
            "reset_filters",
            "jump_latest",
            "open_download_html",
            "open_official_media",
            "jump_to_flip_question",
            "flip_media_play",
            "flip_media_pause",
            "flip_media_seek",
            "flip_media_complete",
        ):
            self.assertIn(action, template)


if __name__ == "__main__":
    unittest.main()

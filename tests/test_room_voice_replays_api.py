from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from website.room_voice_replays_api import _parse_range, router


class RoomVoiceReplaysApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        session_id = "rv_20260717_150000_main_36376935_abcdef"
        session_dir = self.root / "sessions" / session_id
        (session_dir / "segments").mkdir(parents=True)
        (session_dir / "segments" / "segment_000001.m4a").write_bytes(b"0123456789")
        (session_dir / "segments" / "segment_000001_original.m4a").write_bytes(
            b"abcdefghij"
        )
        (session_dir / "session.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "session_id": session_id,
                    "messages_file": "messages.jsonl",
                    "default_playback_mode": "compatible",
                    "available_playback_modes": ["compatible", "original"],
                    "segments": [
                        {
                            "segment_no": 1,
                            "filename": "segments/segment_000001.m4a",
                            "variants": {
                                "compatible": {
                                    "label": "兼容播放",
                                    "filename": "segments/segment_000001.m4a",
                                    "channels": 1,
                                },
                                "original": {
                                    "label": "原始音质",
                                    "filename": "segments/segment_000001_original.m4a",
                                    "channels": 2,
                                },
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (session_dir / "messages.jsonl").write_text(
            json.dumps({"id": "message-1", "text_content": "测试"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (self.root / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "sessions": [{"session_id": session_id}]}),
            encoding="utf-8",
        )
        self.session_id = session_id
        app = FastAPI()
        app.include_router(router)
        self.patches = [
            mock.patch("website.room_voice_replays_api.cfg.ROOM_VOICE_REPLAYS_DIR", str(self.root)),
            mock.patch("website.room_voice_replays_api.cfg.ROOM_VOICE_REPLAYS_PASSWORD", "test-password"),
            mock.patch("website.room_voice_replays_api.cfg.SECURE_COOKIES", False),
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

    async def test_requires_login_and_cookie_unlocks_metadata(self) -> None:
        self.assertEqual((await self.client.get("/api/room-voice-replays/sessions")).status_code, 401)
        login = await self.client.post(
            "/api/room-voice-replays/login", json={"password": "test-password"}
        )
        self.assertEqual(login.status_code, 200)
        sessions = await self.client.get("/api/room-voice-replays/sessions")
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(sessions.json()["sessions"][0]["session_id"], self.session_id)
        detail = await self.client.get(f"/api/room-voice-replays/sessions/{self.session_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["messages"][0]["id"], "message-1")
        segment = detail.json()["session"]["segments"][0]
        self.assertEqual(segment["variants"]["compatible"]["channels"], 1)
        self.assertEqual(segment["variants"]["original"]["channels"], 2)
        self.assertTrue(
            segment["variants"]["original"]["media_url"].endswith(
                "/segment_000001_original.m4a"
            )
        )

    async def test_audio_supports_authenticated_range_requests(self) -> None:
        await self.client.post("/api/room-voice-replays/login", json={"password": "test-password"})
        response = await self.client.get(
            f"/api/room-voice-replays/sessions/{self.session_id}/segments/segment_000001.m4a",
            headers={"Range": "bytes=2-5"},
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"2345")
        self.assertEqual(response.headers["content-range"], "bytes 2-5/10")
        self.assertEqual(response.headers["accept-ranges"], "bytes")

        original = await self.client.get(
            (
                f"/api/room-voice-replays/sessions/{self.session_id}/segments/"
                "segment_000001_original.m4a"
            ),
            headers={"Range": "bytes=1-3"},
        )
        self.assertEqual(original.status_code, 206)
        self.assertEqual(original.content, b"bcd")

    async def test_legacy_single_asset_session_falls_back_to_compatible_mode(self) -> None:
        session_path = self.root / "sessions" / self.session_id / "session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["schema_version"] = 1
        session.pop("default_playback_mode", None)
        session.pop("available_playback_modes", None)
        session["segments"][0].pop("variants", None)
        session_path.write_text(json.dumps(session), encoding="utf-8")

        await self.client.post("/api/room-voice-replays/login", json={"password": "test-password"})
        detail = await self.client.get(f"/api/room-voice-replays/sessions/{self.session_id}")
        variants = detail.json()["session"]["segments"][0]["variants"]
        self.assertIn("compatible", variants)
        self.assertNotIn("original", variants)
        self.assertTrue(variants["compatible"]["media_url"].endswith("segment_000001.m4a"))

    async def test_range_parser_rejects_out_of_bounds(self) -> None:
        self.assertEqual(_parse_range("bytes=-3", 10), (7, 9, True))
        with self.assertRaises(Exception):
            _parse_range("bytes=20-30", 10)


if __name__ == "__main__":
    unittest.main()

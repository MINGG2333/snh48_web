from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from website import social_credentials_admin_api
from website import main as website_main


def client() -> TestClient:
    app = FastAPI()
    app.include_router(social_credentials_admin_api.router)
    return TestClient(app)


class SocialCredentialsAdminApiTests(unittest.TestCase):
    def test_requires_password_and_never_returns_submitted_cookie(self) -> None:
        with (
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_ENABLED", True),
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_PASSWORD", "correct-password"),
            patch.object(social_credentials_admin_api.cfg, "SECURE_COOKIES", False),
            patch.object(social_credentials_admin_api, "_run_bridge", return_value={"ok": True, "platform": "douyin", "slot": "backup"}),
        ):
            web = client()
            self.assertEqual(web.get("/api/social-credentials/status").status_code, 401)
            self.assertEqual(web.post("/api/social-credentials/login", json={"password": "correct-password"}).status_code, 200)
            response = web.post(
                "/api/social-credentials/update",
                headers={"Origin": "http://testserver"},
                json={"platform": "douyin", "slot": "backup", "cookie": "secret-cookie-value-long-enough"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("secret-cookie", response.text)


    def test_stale_cookie_is_login_expired_not_rate_limited(self) -> None:
        with (
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_ENABLED", True),
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_PASSWORD", "correct-password"),
        ):
            web = client()
            for _ in range(12):
                response = web.get(
                    "/api/social-credentials/status",
                    headers={"Cookie": "social_credentials_auth=stale"},
                )
                self.assertEqual(response.status_code, 401)

    def test_xianyu_primary_updates_and_backup_is_rejected(self) -> None:
        with (
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_ENABLED", True),
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_PASSWORD", "correct-password"),
            patch.object(social_credentials_admin_api.cfg, "SECURE_COOKIES", False),
            patch.object(
                social_credentials_admin_api,
                "_run_bridge",
                return_value={"ok": True, "platform": "xianyu", "slot": "primary"},
            ) as run_bridge,
        ):
            web = client()
            web.post("/api/social-credentials/login", json={"password": "correct-password"})
            response = web.post(
                "/api/social-credentials/update",
                headers={"Origin": "http://testserver"},
                json={"platform": "xianyu", "slot": "primary", "cookie": "secret-cookie-value-long-enough"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("secret-cookie", response.text)
            self.assertEqual(run_bridge.call_args.args[1]["platform"], "xianyu")
            rejected = web.post(
                "/api/social-credentials/update",
                headers={"Origin": "http://testserver"},
                json={"platform": "xianyu", "slot": "backup", "cookie": "secret-cookie-value-long-enough"},
            )
            self.assertEqual(rejected.status_code, 422)


    def test_weidian_primary_updates_and_backup_is_rejected(self) -> None:
        with (
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_ENABLED", True),
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_PASSWORD", "correct-password"),
            patch.object(social_credentials_admin_api.cfg, "SECURE_COOKIES", False),
            patch.object(
                social_credentials_admin_api,
                "_run_bridge",
                return_value={"ok": True, "platform": "weidian", "slot": "primary"},
            ) as run_bridge,
        ):
            web = client()
            web.post("/api/social-credentials/login", json={"password": "correct-password"})
            response = web.post(
                "/api/social-credentials/update",
                headers={"Origin": "http://testserver"},
                json={"platform": "weidian", "slot": "primary", "cookie": "secret-weidian-cookie-value-long-enough"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("secret-weidian", response.text)
            self.assertEqual(run_bridge.call_args.args[1]["platform"], "weidian")
            rejected = web.post(
                "/api/social-credentials/update",
                headers={"Origin": "http://testserver"},
                json={"platform": "weidian", "slot": "backup", "cookie": "secret-weidian-cookie-value-long-enough"},
            )
            self.assertEqual(rejected.status_code, 422)


    def test_update_rejects_cross_origin(self) -> None:
        with (
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_ENABLED", True),
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_PASSWORD", "correct-password"),
            patch.object(social_credentials_admin_api.cfg, "SECURE_COOKIES", False),
        ):
            web = client()
            web.post("/api/social-credentials/login", json={"password": "correct-password"})
            response = web.post(
                "/api/social-credentials/update",
                headers={"Origin": "https://example.invalid"},
                json={"platform": "weibo", "slot": "primary", "cookie": "secret-cookie-value-long-enough"},
            )
            self.assertEqual(response.status_code, 403)


    def test_shop48_primary_and_backup_updates_are_accepted(self) -> None:
        with (
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_ENABLED", True),
            patch.object(social_credentials_admin_api.cfg, "SOCIAL_CREDENTIALS_ADMIN_PASSWORD", "correct-password"),
            patch.object(social_credentials_admin_api.cfg, "SECURE_COOKIES", False),
            patch.object(
                social_credentials_admin_api,
                "_run_bridge",
                return_value={"ok": True, "platform": "shop48", "slot": "primary"},
            ) as run_bridge,
        ):
            web = client()
            web.post("/api/social-credentials/login", json={"password": "correct-password"})
            for slot in ("primary", "backup"):
                response = web.post(
                    "/api/social-credentials/update",
                    headers={"Origin": "http://testserver"},
                    json={"platform": "shop48", "slot": slot, "cookie": "secret-shop48-cookie-value-long-enough"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("secret-shop48", response.text)
                self.assertEqual(run_bridge.call_args.args[1]["platform"], "shop48")
                self.assertEqual(run_bridge.call_args.args[1]["slot"], slot)


class SocialCredentialsAdminPageTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_is_not_exposed_on_disabled_nodes(self) -> None:
        with patch.object(website_main.cfg, "SOCIAL_CREDENTIALS_ADMIN_ENABLED", False):
            with self.assertRaises(HTTPException) as raised:
                await website_main.social_credentials_admin_page(None)
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

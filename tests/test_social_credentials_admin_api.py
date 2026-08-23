from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from website import social_credentials_admin_api


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


if __name__ == "__main__":
    unittest.main()

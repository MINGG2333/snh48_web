from __future__ import annotations

import unittest
from unittest import mock

from fastapi import HTTPException, Request, Response

from website.gift_replies_api import (
    router as gift_router,
    verify_gift_replies_login,
)
from website.memories_api import (
    router as memories_router,
    verify_memories_login,
)
from website.ob_api.router import router as ob_router, verify_ob_login
from website.room_messages_api import (
    router as room_router,
    verify_room_messages_login,
)
from website.score_gifts_api import (
    router as score_router,
    verify_score_gifts_login,
)
from website.pk_score_api import router as pk_score_router, verify_pk_score_login


def request_with_header(name: str, value: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(name.lower().encode("ascii"), value.encode("utf-8"))],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


class PasswordVerifyEndpointTests(unittest.TestCase):
    def test_header_auth_routers_expose_protected_lightweight_verify(self) -> None:
        cases = (
            (gift_router, "/api/gift-replies/verify", verify_gift_replies_login),
            (room_router, "/api/room-messages/verify", verify_room_messages_login),
            (score_router, "/api/score-gifts/verify", verify_score_gifts_login),
            (pk_score_router, "/api/pk-score/verify", verify_pk_score_login),
            (ob_router, "/api/ob/verify", verify_ob_login),
        )
        for router, path, endpoint in cases:
            with self.subTest(path=path):
                route = next(route for route in router.routes if route.path == path)
                self.assertTrue(route.dependant.dependencies)
                response = Response()
                self.assertEqual(endpoint(response, _=True), {"verified": True})
                self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_memories_verify_checks_password_without_loading_records(self) -> None:
        route = next(route for route in memories_router.routes if route.path == "/api/memories/verify")
        self.assertEqual(route.endpoint, verify_memories_login)

        with mock.patch("website.memories_api.cfg.MEMORIES_VIEW_PASSWORD", "secret"):
            response = Response()
            payload = verify_memories_login(
                request_with_header("X-Memories-Password", "secret"),
                response,
            )
            self.assertEqual(payload, {"verified": True})
            self.assertEqual(response.headers["Cache-Control"], "no-store")

            with self.assertRaises(HTTPException) as raised:
                verify_memories_login(
                    request_with_header("X-Memories-Password", "wrong"),
                    Response(),
                )
            self.assertEqual(raised.exception.status_code, 403)

    def test_ob_summary_is_password_protected(self) -> None:
        route = next(route for route in ob_router.routes if route.path == "/api/ob/summary")
        self.assertTrue(route.dependant.dependencies)


if __name__ == "__main__":
    unittest.main()

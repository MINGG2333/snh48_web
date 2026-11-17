"""应用层 JSON gzip：只压 JSON，PNG 等压缩格式原样透传。"""
from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.responses import Response
from starlette.testclient import TestClient

from website.json_gzip import JsonGZipMiddleware

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 2048


def _build_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(JsonGZipMiddleware, minimum_size=128)

    @app.get("/json")
    def json_route():
        return {"payload": "x" * 1024}

    @app.get("/small-json")
    def small_json_route():
        return {"ok": True}

    @app.get("/png")
    def png_route():
        return Response(content=PNG_BYTES, media_type="image/png")

    return TestClient(app)


class JsonGZipMiddlewareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _build_client()

    def test_large_json_is_gzipped(self) -> None:
        response = self.client.get("/json", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("content-encoding"), "gzip")
        self.assertIn("Accept-Encoding", response.headers.get("vary", ""))
        self.assertEqual(response.json(), {"payload": "x" * 1024})

    def test_png_is_not_gzipped(self) -> None:
        response = self.client.get("/png", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers.get("content-encoding"), "gzip")
        self.assertEqual(response.content, PNG_BYTES)

    def test_small_json_is_not_gzipped(self) -> None:
        response = self.client.get("/small-json", headers={"Accept-Encoding": "gzip"})
        self.assertNotEqual(response.headers.get("content-encoding"), "gzip")
        self.assertEqual(response.json(), {"ok": True})

    def test_client_without_gzip_support_gets_plain_json(self) -> None:
        response = self.client.get("/json", headers={"Accept-Encoding": "identity"})
        self.assertNotEqual(response.headers.get("content-encoding"), "gzip")
        self.assertEqual(len(response.json()["payload"]), 1024)

    def test_head_request_is_not_compressed(self) -> None:
        response = self.client.head("/json", headers={"Accept-Encoding": "gzip"})
        self.assertNotEqual(response.headers.get("content-encoding"), "gzip")


if __name__ == "__main__":
    unittest.main()

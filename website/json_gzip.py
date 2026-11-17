"""Gzip only JSON responses.

nginx 默认只压缩 text/html，红蓝台账的 ``/api/redblue/data`` 一次要传 600KB+
JSON。这里在应用层只压缩 ``application/json``，PNG/ZIP 等已经是压缩格式的响应
原样透传，避免给 3MB 的导出图再压一遍。
"""
from __future__ import annotations

import gzip

DEFAULT_MINIMUM_SIZE = 1024
DEFAULT_COMPRESS_LEVEL = 6


class JsonGZipMiddleware:
    def __init__(
        self,
        app,
        minimum_size: int = DEFAULT_MINIMUM_SIZE,
        compress_level: int = DEFAULT_COMPRESS_LEVEL,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compress_level = compress_level

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") == "HEAD":
            await self.app(scope, receive, send)
            return
        request_headers = dict(scope.get("headers") or [])
        accept_encoding = request_headers.get(b"accept-encoding", b"").decode("latin-1").lower()
        if "gzip" not in accept_encoding:
            await self.app(scope, receive, send)
            return

        status = 0
        response_headers: list[tuple[bytes, bytes]] = []
        body = bytearray()
        compressible = False

        async def send_wrapper(message) -> None:
            nonlocal status, response_headers, compressible
            if message["type"] == "http.response.start":
                status = int(message["status"])
                response_headers = list(message.get("headers") or [])
                content_type = ""
                for key, value in response_headers:
                    if key.lower() == b"content-type":
                        content_type = value.decode("latin-1").lower()
                        break
                compressible = (
                    "application/json" in content_type
                    and 200 <= status < 300
                    and not any(key.lower() == b"content-encoding" for key, _ in response_headers)
                )
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            body.extend(message.get("body") or b"")
            if message.get("more_body"):
                return
            payload = bytes(body)
            headers = response_headers
            if compressible and len(payload) >= self.minimum_size:
                payload = gzip.compress(payload, self.compress_level)
                headers = [
                    (key, value)
                    for key, value in response_headers
                    if key.lower() not in (b"content-length", b"content-encoding")
                ]
                headers.append((b"content-encoding", b"gzip"))
                headers.append((b"vary", b"Accept-Encoding"))
                headers.append((b"content-length", str(len(payload)).encode("latin-1")))
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": payload, "more_body": False})

        await self.app(scope, receive, send_wrapper)

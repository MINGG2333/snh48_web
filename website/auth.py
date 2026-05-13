"""
Simple password-based authentication for API endpoints.

Usage:
    export SITE_PASSWORD="your_secret_password"
    python -m website.main

Clients must include the header "X-Site-Password: your_secret_password"
to access protected endpoints.
"""
from __future__ import annotations

import hmac
from fastapi import Header, HTTPException, status

from website import config as cfg


async def verify_password(x_site_password: str = Header(None, alias="X-Site-Password")):
    """
    FastAPI dependency: verify the site password from request header.

    Usage in router:
        @router.post("/ask")
        def ask_question(req: AskRequest, _=Depends(verify_password)):
            ...

    If SITE_PASSWORD is not set, the feature is disabled.
    """
    if not cfg.SITE_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI 问答功能未启用。请通知管理员设置以启用此功能。",
        )

    if not x_site_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要密码才能访问。请在请求头中携带 X-Site-Password。",
        )

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(cfg.SITE_PASSWORD, x_site_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="密码错误，拒绝访问。",
        )

    return True

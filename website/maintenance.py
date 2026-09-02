"""Node-local maintenance guard for public-site migrations."""

from __future__ import annotations

from fastapi import HTTPException, status

from website import config as cfg


def ensure_writable() -> None:
    """Reject business writes while a node is being drained for migration."""
    if not cfg.SITE_MAINTENANCE_MODE:
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=cfg.SITE_MAINTENANCE_MESSAGE,
        headers={"Retry-After": str(cfg.SITE_MAINTENANCE_RETRY_AFTER_SECONDS)},
    )

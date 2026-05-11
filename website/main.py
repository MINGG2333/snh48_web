#!/usr/bin/env python3
"""
SNH48 演艺信息站 - FastAPI Application
"""
from __future__ import annotations

import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from website import config as cfg

app = FastAPI(
    title=cfg.SITE_TITLE,
    description=cfg.SITE_DESCRIPTION,
    version="0.1.0",
)

# ── Static Files ───────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(cfg.STATIC_DIR)), name="static")

# ── Templates ──────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(cfg.TEMPLATES_DIR))


# ── Frontend Page Routes ───────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page with fullscreen background and floating/sliding text."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_description": cfg.SITE_DESCRIPTION,
        },
    )


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    return templates.TemplateResponse(
        "about.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
        },
    )


@app.get("/qa", response_class=HTMLResponse)
async def qa_page(request: Request):
    """AI Q&A page."""
    return templates.TemplateResponse(
        "qa.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_description": cfg.SITE_DESCRIPTION,
        },
    )


# ── API Routes ─────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    """Try to load the QA engine on startup (non-blocking on failure)."""
    try:
        from website.qa_api.router import _get_qa_engine
        _get_qa_engine()
        print("✓ QA engine initialization attempted.")
    except Exception as e:
        print(f"! QA engine not available at startup: {e}")
        print("  You can still serve the frontend. Build the KB later via API.")


# Must be imported last to avoid circular imports
from website.qa_api.router import router as qa_router
app.include_router(qa_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("website.main:app", host=cfg.HOST, port=cfg.PORT, reload=True)

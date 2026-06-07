#!/usr/bin/env python3
"""
SNH48 演艺信息站 - FastAPI Application
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from website import config as cfg

app = FastAPI(
    title=cfg.SITE_TITLE,
    description=cfg.SITE_DESCRIPTION,
    version="0.1.0",
)

# ── Static Files ───────────────────────────────────────────────────────────
# Mount JS separately first (may be obfuscated in production)
# The more-specific /static/js mount must come BEFORE the general /static mount
if cfg.USE_OBFUSCATED_JS:
    _js_dir = cfg.STATIC_DIR / "js-dist"
    if _js_dir.exists():
        app.mount("/static/js", StaticFiles(directory=str(_js_dir)), name="static_js")
app.mount("/static", StaticFiles(directory=str(cfg.STATIC_DIR)), name="static")

# ── Live Covers (mount for fast static serving) ───────────────────────────
from pathlib import Path as _Path
# Try new live_push_replays covers first, then fall back to old room_record
_covers_candidates = [
    _Path(cfg.LIVE_PUSH_REPLAY_ROOT) / "陈嘉仪_161808449" / "covers",
    _Path(cfg.LIVE_PUSH_REPLAY_ROOT) / "陈嘉仪_161808449" / "live_covers",
    _Path("/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/covers"),
    _Path("/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/live_covers"),
    _Path("/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers"),
]
for _p in _covers_candidates:
    if _p.exists():
        app.mount("/live-covers", StaticFiles(directory=str(_p)), name="live_covers")
        break



# ── Templates ──────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(cfg.TEMPLATES_DIR))


# ── Cache Busting Helper ──────────────────────────────────────────────────
def static_version(filename: str) -> str:
    """Return version string based on file modification time for cache busting."""
    filepath = cfg.STATIC_DIR / filename.lstrip("/")
    if filepath.exists():
        return str(int(os.path.getmtime(filepath)))
    return "1"


# ── Favicon (random rotation) ──────────────────────────────────────────────

FAVICON_DIR = cfg.STATIC_DIR / "images" / "favicons"


@app.get("/favicon.ico")
async def favicon():
    """Randomly pick one favicon from the favicons directory each request."""
    if not FAVICON_DIR.is_dir():
        return HTMLResponse(status_code=204)
    icons = sorted(FAVICON_DIR.glob("favicon*.png"))
    if not icons:
        return HTMLResponse(status_code=204)
    chosen = random.choice(icons)
    return FileResponse(
        chosen,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ── Simple CAPTCHA helper for complaint form ────────────────────────────────


def _generate_captcha() -> tuple[str, str]:
    """Generate a simple arithmetic CAPTCHA question and answer."""
    a = random.randint(1, 20)
    b = random.randint(1, 9)
    op = random.choice(["+", "-"])
    if op == "-" and a < b:
        a, b = b, a
    if op == "+":
        answer = str(a + b)
    else:
        answer = str(a - b)
    question = f"{a} {op} {b} = ?"
    return question, answer


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
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
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
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
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
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "site_domain": cfg.SITE_DOMAIN,
            "static_version": static_version,
            # QA config injected server-side as JSON (not in static JS)
            "qa_config_json": json.dumps({
                "timeout_seconds": cfg.QA_TIMEOUT_SECONDS,
                "poll_interval_ms": cfg.QA_POLL_INTERVAL_MS,
                "warn_seconds": cfg.QA_WARN_SECONDS,
                "max_question_length": 20,
            }),
        },
    )


@app.get("/timeline", response_class=HTMLResponse)
async def timeline_page(request: Request):
    """Timeline page showing Chen Jiayi's journey."""
    return templates.TemplateResponse(
        "timeline.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
        },
    )


@app.get("/replay/{live_id}", response_class=HTMLResponse)
async def replay_page(request: Request, live_id: str):
    """Replay video player page with custom controls."""
    # Look up replay_url from summary CSV
    replay_url = ""
    title = "直播回放"
    date = ""
    try:
        import csv
        from pathlib import Path
        csv_paths = [
            Path(cfg.LIVE_PUSH_REPLAY_ROOT) / "陈嘉仪_161808449" / "summary.csv",
            Path("/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/summary.csv"),
        ]
        for csv_path in csv_paths:
            if csv_path.exists():
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if (row.get("live_id") or "").strip() == live_id:
                            play_url = (row.get("play_url") or "").strip()
                            vstatus = (row.get("video_status") or "").strip()
                            if play_url and vstatus in ("available", "downloaded"):
                                replay_url = play_url
                            title = (row.get("title") or "").strip() or "直播回放"
                            date = (row.get("push_bj") or "").strip()
                            break
                break
    except Exception:
        pass

    return templates.TemplateResponse(
        "replay.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
            "replay_url": replay_url or "",
            "live_id": live_id,
            "title": title,
            "date": date,
        },
    )


@app.get("/scroller-admin", response_class=HTMLResponse)
async def scroller_admin_page(request: Request):
    """Scroller text management page."""
    return templates.TemplateResponse(
        "scroller_admin.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
        },
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms of Service page."""
    return templates.TemplateResponse(
        "terms.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
        },
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy Policy page."""
    return templates.TemplateResponse(
        "privacy.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
        },
    )


@app.get("/complaint", response_class=HTMLResponse)
async def complaint_page(request: Request):
    """Complaint & Report page."""
    captcha_question, captcha_answer = _generate_captcha()
    return templates.TemplateResponse(
        "complaint.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
            "captcha_question": captcha_question,
            "captcha_answer": captcha_answer,
        },
    )


@app.get("/ob", response_class=HTMLResponse)
async def ob_page(request: Request):
    """Admin observation page - user activity grouped by IP."""
    return templates.TemplateResponse(
        "ob.html",
        {
            "request": request,
            "site_title": cfg.SITE_TITLE,
            "site_icp": cfg.SITE_ICP,
            "site_police_icp": cfg.SITE_POLICE_ICP,
            "site_police_icp_code": cfg.SITE_POLICE_ICP_CODE,
            "static_version": static_version,
        },
    )


# ── API Routes ─────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    """
    On startup:
    1. Back up old qa_archive, video_knowledge_db, transcript_analyze (if configured)
    2. Initialize interaction log session
    3. Try to load the QA engine (non-blocking on failure)
    """
    kb_dir = Path(cfg.KB_DIR)
    if kb_dir.exists():
        from website.logging_setup import backup_and_recreate_qa_archive
        backed_up = backup_and_recreate_qa_archive(kb_dir)
        if backed_up:
            print(f"✓ qa_archive backed up successfully at {kb_dir}")
    else:
        print(f"  KB directory {kb_dir} does not exist yet, skipping qa_archive backup.")

    transcript_dir = Path(__file__).resolve().parent.parent / "transcript_analyze"
    if transcript_dir.exists():
        _backup_log_files(transcript_dir)

    from website.logging_setup import get_session_dir
    session_dir = get_session_dir()
    print(f"✓ Interaction log session started: {session_dir}")

    try:
        from website.qa_api.router import _get_qa_engine
        _get_qa_engine()
        print("✓ QA engine initialization attempted.")
    except Exception as e:
        print(f"! QA engine not available at startup: {e}")
        print("  You can still serve the frontend. Build the KB later via API.")


def _backup_log_files(transcript_dir: Path) -> None:
    """Backup existing log files in various locations."""
    import shutil
    from datetime import datetime

    log_files = [
        transcript_dir / "kb_qa.log",
        transcript_dir.parent / "kb_qa.log",
        transcript_dir.parent / "snh48_screen.log",
    ]

    server_log_dir = Path("/var/log/snh48")
    if server_log_dir.exists():
        for f in server_log_dir.iterdir():
            if f.is_file() and f.suffix in (".log", ""):
                log_files.append(f)

    backup_dir = transcript_dir / "logs_backup"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for log_file in log_files:
        if log_file.exists() and log_file.stat().st_size > 0:
            try:
                backup_name = f"{log_file.name}_{timestamp}"
                backup_path = backup_dir / backup_name
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(log_file), str(backup_path))
                log_file.write_text("")
                print(f"✓ Backed up {log_file.name} → logs_backup/{backup_name}")
            except OSError as e:
                print(f"  ! Failed to backup {log_file.name}: {e}")


# Must be imported last to avoid circular imports
from website.qa_api.router import router as qa_router
app.include_router(qa_router)

from website.scroller_api.router import router as scroller_router
app.include_router(scroller_router)

from website.complaint_api.router import router as complaint_router
app.include_router(complaint_router)

from website.track_api.router import router as track_router
app.include_router(track_router)

from website.balance_api.router import router as balance_router  # CHANGED: 新增余额查询接口
app.include_router(balance_router)  # CHANGED

from website.timeline_api.router import router as timeline_router
app.include_router(timeline_router)

from website.ob_api.router import router as ob_router
app.include_router(ob_router)


# ── Security Headers Middleware ─────────────────────────────────────────────


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security-related HTTP headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("website.main:app", host=cfg.HOST, port=cfg.PORT, reload=False)

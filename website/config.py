"""
Website configuration.
Reads from environment variables with sensible defaults for local development.
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Project Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # snh48_web/
WEBSITE_DIR = PROJECT_ROOT / "website"
STATIC_DIR = WEBSITE_DIR / "static"
TEMPLATES_DIR = WEBSITE_DIR / "templates"

# ── Transcript Knowledge Base ──────────────────────────────────────────────
RECORDS_PATH = os.getenv("RECORDS_PATH", str(PROJECT_ROOT / "download_records.json"))
SUBTITLE_ROOT = os.getenv("SUBTITLE_ROOT", str(PROJECT_ROOT / "firered_output_batch"))
KB_DIR = os.getenv("KB_DIR", str(PROJECT_ROOT / "video_knowledge_db"))

# ── LLM / AI ───────────────────────────────────────────────────────────────
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
LLM_API_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "shibing624/text2vec-base-chinese")

# ── Server ─────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── Website Metadata ───────────────────────────────────────────────────────
SITE_TITLE = os.getenv("SITE_TITLE", "SNH48 演艺信息站")
SITE_DESCRIPTION = os.getenv(
    "SITE_DESCRIPTION",
    "记录喜爱的演艺人员公开信息，基于 AI 的视频内容问答",
)

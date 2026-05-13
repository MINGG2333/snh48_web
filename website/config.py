"""
Website configuration.
Reads from environment variables with sensible defaults for local development.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Project Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # snh48_web/
WEBSITE_DIR = PROJECT_ROOT / "website"
STATIC_DIR = WEBSITE_DIR / "static"
TEMPLATES_DIR = WEBSITE_DIR / "templates"

# ── Load .env file if present (must be before any os.getenv call) ──────────
# .env 已被 .gitignore 排除，密码写在里面不会进 Git 历史
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            # 环境变量优先，.env 里的值仅当未设置环境变量时生效
            if key not in os.environ:
                os.environ[key] = val

# ── Transcript Knowledge Base ──────────────────────────────────────────────
# 数据文件/目录默认放在 transcript_analyze/ 下（与 run_kb_qa.py 同目录）
RECORDS_PATH = os.getenv("RECORDS_PATH", str(PROJECT_ROOT / "transcript_analyze" / "download_records.json"))
SUBTITLE_ROOT = os.getenv("SUBTITLE_ROOT", str(PROJECT_ROOT / "transcript_analyze" / "firered_output_batch"))
# 知识库目录：优先取环境变量，否则自动检测（兼容 transcript_analyze 下或项目根目录）
_default_kb_dir = str(PROJECT_ROOT / "transcript_analyze" / "video_knowledge_db")
_fallback_kb_dir = str(PROJECT_ROOT / "video_knowledge_db")
if not Path(_default_kb_dir).exists() and Path(_fallback_kb_dir).exists():
    _default_kb_dir = _fallback_kb_dir
KB_DIR = os.getenv("KB_DIR", _default_kb_dir)

# ── LLM / AI ───────────────────────────────────────────────────────────────
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
LLM_API_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "shibing624/text2vec-base-chinese")

# ── Security ────────────────────────────────────────────────────────────────
# 网站密码保护：设置后访问 API 需要提供此密码（环境变量 SITE_PASSWORD）
# 留空则不做密码验证（仅建议在开发/内网环境留空）
#
# 推荐做法：在项目根目录创建 .env 文件（会被 .gitignore 排除，不会进 Git）：
#   SITE_PASSWORD=xxxxxxxxx
#   同时可在 .env 中设置 DEEPSEEK_API_KEY 等其他敏感变量
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "")

# ── Server ─────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── Website Metadata ───────────────────────────────────────────────────────
SITE_TITLE = os.getenv("SITE_TITLE", "心上珍藏集")
SITE_DESCRIPTION = os.getenv(
    "SITE_DESCRIPTION",
    "记录 SNH48陈嘉仪 的公开信息，提供基于 LLM 的 AI 问答",
)

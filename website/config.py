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
            # 去掉行内 # 注释（避免 "10           # 注释" 导致 int() 解析失败）
            if "#" in val:
                val = val.partition("#")[0].strip()
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
# AI 问答功能必须设置密码才能使用（环境变量 SITE_PASSWORD）
# 留空则 AI 问答功能将被禁用
#
# 推荐做法：在项目根目录创建 .env 文件（会被 .gitignore 排除，不会进 Git）：
#   SITE_PASSWORD=xxxxxxxxx
#   同时可在 .env 中设置 DEEPSEEK_API_KEY 等其他敏感变量
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "")

# 背景词管理密码（独立于 AI 问答密码，环境变量 SCROLLER_PASSWORD）
# 留空则背景词管理功能将被禁用
SCROLLER_PASSWORD = os.getenv("SCROLLER_PASSWORD", "")

# 观察页管理密码（独立密码，环境变量 OB_PASSWORD）
# 观察页用于管理员查看用户使用情况（按 IP 分组）
# 留空则观察页功能将被禁用
OB_PASSWORD = os.getenv("OB_PASSWORD", "")

# ── Rate Limiting (防滥用配置) ──────────────────────────────────────────────
# 所有值均可通过 .env 文件或环境变量覆盖

# 每个 IP 在时间窗口内最多允许多少次 QA 提问（默认：每 60 秒最多 5 次）
QA_RATE_LIMIT_PER_WINDOW = int(os.getenv("QA_RATE_LIMIT_PER_WINDOW", "5"))
QA_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("QA_RATE_LIMIT_WINDOW_SECONDS", "60"))

# 每个用户在两次提问之间必须等待的最小间隔（秒）（默认：30 秒）
QA_USER_COOLDOWN_SECONDS = int(os.getenv("QA_USER_COOLDOWN_SECONDS", "30"))

# 每个用户每日最大提问次数（默认：50 次/天）
QA_DAILY_QUOTA_PER_USER = int(os.getenv("QA_DAILY_QUOTA_PER_USER", "50"))

# CHANGED: 每个 IP 每天最多提问次数（持久化，重启不丢失）
QA_DAILY_IP_QUOTA = int(os.getenv("QA_DAILY_IP_QUOTA", "5"))

# 每个用户最多同时处理的任务数（默认：2 个）
QA_MAX_CONCURRENT_PER_USER = int(os.getenv("QA_MAX_CONCURRENT_PER_USER", "2"))

# 密码验证限制：每个 IP 在时间窗口内最多尝试次数（防暴力破解）（默认：每 300 秒最多 10 次）
PASSWORD_RATE_LIMIT_PER_WINDOW = int(os.getenv("PASSWORD_RATE_LIMIT_PER_WINDOW", "10"))
PASSWORD_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("PASSWORD_RATE_LIMIT_WINDOW_SECONDS", "300"))

# ── QA 前端配置（通过 /api/qa/config 暴露给前端，不硬编码在 JS 中）─────────
# Nginx proxy 超时时间（秒），前端轮询超过此时间后显示超时提示
QA_TIMEOUT_SECONDS = int(os.getenv("QA_TIMEOUT_SECONDS", "300"))
# 前端轮询间隔（毫秒）
QA_POLL_INTERVAL_MS = int(os.getenv("QA_POLL_INTERVAL_MS", "3000"))
# 超时预警时间（秒），超过此时间前端显示警告
QA_WARN_SECONDS = int(os.getenv("QA_WARN_SECONDS", "240"))

# ── 通用公开端点限速（防滥用）────────────────────────────────────────────────
# Scroller 登录限速（防暴力破解）
SCROLLER_LOGIN_MAX_PER_WINDOW = int(os.getenv("SCROLLER_LOGIN_MAX_PER_WINDOW", "10"))
SCROLLER_LOGIN_WINDOW_SECONDS = int(os.getenv("SCROLLER_LOGIN_WINDOW_SECONDS", "300"))

# 邮箱提交限速（防垃圾邮箱提交）
EMAIL_SUBMIT_MAX_PER_WINDOW = int(os.getenv("EMAIL_SUBMIT_MAX_PER_WINDOW", "5"))
EMAIL_SUBMIT_WINDOW_SECONDS = int(os.getenv("EMAIL_SUBMIT_WINDOW_SECONDS", "300"))

# 行为追踪事件限速（防伪造事件洪水）
TRACK_EVENT_MAX_PER_WINDOW = int(os.getenv("TRACK_EVENT_MAX_PER_WINDOW", "30"))
TRACK_EVENT_WINDOW_SECONDS = int(os.getenv("TRACK_EVENT_WINDOW_SECONDS", "60"))

# 投诉提交限速（防恶意刷投诉）
COMPLAINT_MAX_PER_WINDOW = int(os.getenv("COMPLAINT_MAX_PER_WINDOW", "3"))
COMPLAINT_WINDOW_SECONDS = int(os.getenv("COMPLAINT_WINDOW_SECONDS", "600"))

# ── Live Push Replays (直播汇总，含回放信息，替代旧的 room_record) ─────────
# summary.csv 所在目录，由 live_push_replay_matcher.py 生成
# 服务器上：/home/snh48-fan-hub/live_push_replays/
LIVE_PUSH_REPLAY_ROOT = os.getenv(
    "LIVE_PUSH_REPLAY_ROOT",
    str(PROJECT_ROOT.parent / "snh48-fan-hub" / "live_push_replays"),
)

# ── Schedule CSV (行程表，由 schedule_monitor.py 生成) ──────────────────────
# 服务器上：/home/snh48-fan-hub/schedule_record/schedule.csv
SCHEDULE_CSV_PATH = os.getenv(
    "SCHEDULE_CSV_PATH",
    str(PROJECT_ROOT.parent / "snh48-fan-hub" / "schedule_record" / "schedule.csv"),
)

# ── Manual Events CSV (手动事件，修改后无需重启即可生效) ─────────────────
MANUAL_EVENTS_CSV_PATH = os.getenv(
    "MANUAL_EVENTS_CSV_PATH",
    str(WEBSITE_DIR / "data" / "manual_events.csv"),
)

# ── Server ─────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
SITE_DOMAIN = os.getenv("SITE_DOMAIN", "")

# ── Website Metadata ───────────────────────────────────────────────────────
SITE_TITLE = os.getenv("SITE_TITLE", "心上珍藏集")
SITE_DESCRIPTION = os.getenv(
    "SITE_DESCRIPTION",
    "记录 SNH48陈嘉仪 的公开信息，提供基于 LLM 的 AI 问答",
)

# ── ICP 备案号（可选）────────────────────────────────────────────────────────
# 备案完成后在此填写，会在页面底部显示备案号并链接到工信部
# 可通过 .env 文件或环境变量设置
SITE_ICP = os.getenv("SITE_ICP", "")

# 公安联网备案号（可选，备案审核通过后填写）
SITE_POLICE_ICP = os.getenv("SITE_POLICE_ICP", "")

# 从公安备案号中提取 code（用于链接到公安部查询页面）
# 例如 "京公网安备11010602202601号" → "11010602202601"
SITE_POLICE_ICP_CODE = os.getenv("SITE_POLICE_ICP_CODE", "")
if not SITE_POLICE_ICP_CODE and SITE_POLICE_ICP:
    # 自动提取：去掉"京公网安备"前缀和"号"后缀
    import re
    match = re.search(r"(\d+)", SITE_POLICE_ICP)
    if match:
        SITE_POLICE_ICP_CODE = match.group(1)

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
SCROLLER_TEXTS_PATH = os.getenv(
    "SCROLLER_TEXTS_PATH",
    str(PROJECT_ROOT / "website" / "data" / "scroller_texts.json"),
)

# 观察页管理密码（独立密码，环境变量 OB_PASSWORD）
# 观察页用于管理员查看用户使用情况（按 IP 分组）
# 留空则观察页功能将被禁用
OB_PASSWORD = os.getenv("OB_PASSWORD", "")

# 翻牌记录页密码。默认复用 OB_PASSWORD；如需单独管理可设置 FLIP_CARDS_PASSWORD。
# 翻牌记录和媒体都只能通过鉴权 API 读取，不做静态目录挂载。
FLIP_CARDS_PASSWORD = os.getenv("FLIP_CARDS_PASSWORD") or OB_PASSWORD

# 礼物回复页管理密码（独立密码，环境变量 GIFT_REPLIES_PASSWORD）
# 留空则礼物回复页 API 将被禁用
GIFT_REPLIES_PASSWORD = os.getenv("GIFT_REPLIES_PASSWORD", "")

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
# 是否在服务启动时后台预热 QA 知识库。默认开启，保持现有 QA 页面行为；调试管理页冷启动时可临时设为 false。
QA_WARMUP_ON_STARTUP = os.getenv("QA_WARMUP_ON_STARTUP", "true").lower() in ("1", "true", "yes")

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

# 余额状态接口缓存和限速（避免公开状态页触发外部 API 请求洪水）
BALANCE_CACHE_SECONDS = int(os.getenv("BALANCE_CACHE_SECONDS", "300"))
BALANCE_MAX_PER_WINDOW = int(os.getenv("BALANCE_MAX_PER_WINDOW", "10"))
BALANCE_WINDOW_SECONDS = int(os.getenv("BALANCE_WINDOW_SECONDS", "60"))

# OB 观察页密码错误尝试限速
OB_LOGIN_MAX_PER_WINDOW = int(os.getenv("OB_LOGIN_MAX_PER_WINDOW", "10"))
OB_LOGIN_WINDOW_SECONDS = int(os.getenv("OB_LOGIN_WINDOW_SECONDS", "300"))

# 生产环境默认只通过 HTTPS 发送管理 Cookie；本地 HTTP 调试可设为 false
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "true").lower() not in ("0", "false", "no")

# 可信反向代理来源。默认只信任本机 Nginx；Docker/多层反代需显式添加真实代理 IP/CIDR。
TRUSTED_PROXY_PEERS = tuple(
    item.strip()
    for item in os.getenv("TRUSTED_PROXY_PEERS", "127.0.0.1,::1").split(",")
    if item.strip()
)

# ── Live Push Replays (直播汇总，含回放信息，替代旧的 room_record) ─────────
# summary.csv 所在目录，由 live_push_replay_matcher.py 生成
# 服务器上：/home/snh48-fan-hub/live_push_replays/
LIVE_PUSH_REPLAY_ROOT = os.getenv(
    "LIVE_PUSH_REPLAY_ROOT",
    str(PROJECT_ROOT.parent / "snh48-fan-hub" / "live_push_replays"),
)

# ── Gift Replies (口袋房间礼物回复状态) ─────────────────────────────────────
# 由 snh48-fan-hub/scripts/live_monitor/gift_reply_exporter.py 生成
GIFT_REPLIES_DIR = os.getenv(
    "GIFT_REPLIES_DIR",
    str(
        PROJECT_ROOT.parent
        / "snh48-fan-hub"
        / "room_record"
        / "陈嘉仪_161808449"
        / "gift_replies"
    ),
)

# ── Room Messages (口袋房间完整消息记录) ────────────────────────────────────
# 默认复用礼物回复页密码；如需单独管理可设置 ROOM_MESSAGES_PASSWORD。
ROOM_MESSAGES_PASSWORD = os.getenv("ROOM_MESSAGES_PASSWORD", GIFT_REPLIES_PASSWORD)
ROOM_MESSAGES_CSV_PATH = os.getenv(
    "ROOM_MESSAGES_CSV_PATH",
    str(
        PROJECT_ROOT.parent
        / "snh48-fan-hub"
        / "room_record"
        / "陈嘉仪_161808449"
        / "messages.csv"
    ),
)
ROOM_MESSAGES_SHARDS_DIR = os.getenv(
    "ROOM_MESSAGES_SHARDS_DIR",
    str(
        PROJECT_ROOT.parent
        / "snh48-fan-hub"
        / "room_record"
        / "陈嘉仪_161808449"
        / "messages_shards"
    ),
)
ROOM_AUDIO_TRANSCRIPTS_PATH = os.getenv(
    "ROOM_AUDIO_TRANSCRIPTS_PATH",
    str(
        PROJECT_ROOT.parent
        / "snh48-fan-hub"
        / "room_record"
        / "陈嘉仪_161808449"
        / "audio_transcripts"
        / "room_audio_transcripts.jsonl"
    ),
)
ROOM_MESSAGES_IGNORE_PATH = os.getenv(
    "ROOM_MESSAGES_IGNORE_PATH",
    str(PROJECT_ROOT / "website" / "data" / "room_messages_ignored_batches.json"),
)
# Legacy direct-sync values are read only as rollout defaults for the shared
# runtime-state transport. The room endpoint no longer contains Git sync or
# whole-file peer overwrite code.
ROOM_MESSAGES_IGNORE_DIRECT_SYNC = os.getenv("ROOM_MESSAGES_IGNORE_DIRECT_SYNC", "false").lower() not in (
    "0",
    "false",
    "no",
)
ROOM_MESSAGES_IGNORE_DIRECT_PEER = os.getenv("ROOM_MESSAGES_IGNORE_DIRECT_PEER", "")
ROOM_MESSAGES_IGNORE_DIRECT_CONNECT_TIMEOUT_SECONDS = int(
    os.getenv("ROOM_MESSAGES_IGNORE_DIRECT_CONNECT_TIMEOUT_SECONDS", "3")
)
ROOM_MESSAGES_IGNORE_DIRECT_TIMEOUT_SECONDS = int(os.getenv("ROOM_MESSAGES_IGNORE_DIRECT_TIMEOUT_SECONDS", "10"))
ROOM_MESSAGES_REFRESH_INTERVAL_SECONDS = int(os.getenv("ROOM_MESSAGES_REFRESH_INTERVAL_SECONDS", "60"))

# ── Room Voice Replays (成员房间上麦录音与同期消息) ───────────────────────
# 默认复用房间消息页密码；音频只能通过鉴权 API 读取，不做静态目录挂载。
ROOM_VOICE_REPLAYS_PASSWORD = os.getenv("ROOM_VOICE_REPLAYS_PASSWORD") or ROOM_MESSAGES_PASSWORD
ROOM_VOICE_REPLAYS_DIR = os.getenv("ROOM_VOICE_REPLAYS_DIR") or str(
    PROJECT_ROOT.parent
    / "snh48-fan-hub"
    / "room_record"
    / "陈嘉仪_161808449"
    / "room_voice_replays"
)

# ── Flip Cards (口袋48翻牌记录 HTML 与本地媒体) ───────────────────────
FLIP_CARDS_HTML_PATH = os.getenv("FLIP_CARDS_HTML_PATH") or str(
    PROJECT_ROOT.parent / "snh48-fan-hub" / "flip_chat.html"
)
FLIP_CARDS_DATA_DIR = os.getenv("FLIP_CARDS_DATA_DIR") or str(
    PROJECT_ROOT.parent / "snh48-fan-hub" / "flip_data"
)

# ── Score Gifts (计分礼物统计页) ─────────────────────────────────────
# 默认复用礼物回复页密码；如需单独管理可设置 SCORE_GIFTS_PASSWORD。
SCORE_GIFTS_PASSWORD = os.getenv("SCORE_GIFTS_PASSWORD", GIFT_REPLIES_PASSWORD)
SCORE_GIFTS_DATA_PATH = os.getenv(
    "SCORE_GIFTS_DATA_PATH",
    str(
        PROJECT_ROOT.parent
        / "snh48-fan-hub"
        / "room_record"
        / "陈嘉仪_161808449"
        / "score_gifts"
        / "score_gifts.json"
    ),
)

# ── Memories (粉丝与陈嘉仪的互动记忆) ─────────────────────────────────
# 页面访问/提交密码；留空则记忆页 API 禁用，避免未设置密码时误公开。
MEMORIES_VIEW_PASSWORD = os.getenv("MEMORIES_VIEW_PASSWORD", "")
# 应援会模式密码：可查看待审内容、通过/拒绝审核、标记应援会确认。
MEMORIES_FANCLUB_PASSWORD = os.getenv("MEMORIES_FANCLUB_PASSWORD", "")
# 本人模式密码：可查看已公开待确认记忆并标记本人确认。
MEMORIES_IDOL_PASSWORD = os.getenv("MEMORIES_IDOL_PASSWORD", "")
MEMORIES_DATA_PATH = os.getenv(
    "MEMORIES_DATA_PATH",
    str(PROJECT_ROOT / "website" / "data" / "memories" / "memories.json"),
)
MEMORIES_START_DATE = os.getenv("MEMORIES_START_DATE", "2025-09-01")
MEMORIES_SUBMIT_ENABLED = os.getenv("MEMORIES_SUBMIT_ENABLED", "true").lower() not in (
    "0",
    "false",
    "no",
)
MEMORIES_SUBMIT_MAX_PER_WINDOW = int(os.getenv("MEMORIES_SUBMIT_MAX_PER_WINDOW", "5"))
MEMORIES_SUBMIT_WINDOW_SECONDS = int(os.getenv("MEMORIES_SUBMIT_WINDOW_SECONDS", "600"))

# ── Versioned runtime state shared by Tencent and Aliyun ───────────────
# Existing ROOM_MESSAGES_IGNORE_DIRECT_* values are accepted as migration
# defaults so rollout does not require exposing or replacing SSH credentials.
_shared_state_domain = os.getenv("SITE_DOMAIN", "")
_shared_state_default_node = (
    "aliyun" if ("xn--" in _shared_state_domain or "我爱你" in _shared_state_domain) else "tencent"
)
SHARED_STATE_NODE_ID = os.getenv("SHARED_STATE_NODE_ID", _shared_state_default_node).strip().lower()
SHARED_STATE_IS_PRIMARY = os.getenv(
    "SHARED_STATE_IS_PRIMARY",
    "true" if SHARED_STATE_NODE_ID == "tencent" else "false",
).lower() not in ("0", "false", "no")
SHARED_STATE_SYNC_ENABLED = os.getenv(
    "SHARED_STATE_SYNC_ENABLED",
    "true" if ROOM_MESSAGES_IGNORE_DIRECT_SYNC else "false",
).lower() not in ("0", "false", "no")
SHARED_STATE_PEER = os.getenv("SHARED_STATE_PEER", ROOM_MESSAGES_IGNORE_DIRECT_PEER).strip()
SHARED_STATE_CONNECT_TIMEOUT_SECONDS = int(
    os.getenv("SHARED_STATE_CONNECT_TIMEOUT_SECONDS", str(ROOM_MESSAGES_IGNORE_DIRECT_CONNECT_TIMEOUT_SECONDS))
)
SHARED_STATE_TIMEOUT_SECONDS = int(
    os.getenv("SHARED_STATE_TIMEOUT_SECONDS", str(max(ROOM_MESSAGES_IGNORE_DIRECT_TIMEOUT_SECONDS, 20)))
)
SHARED_STATE_RETRY_INTERVAL_SECONDS = int(os.getenv("SHARED_STATE_RETRY_INTERVAL_SECONDS", "60"))
SHARED_STATE_REMOTE_ROOT = os.getenv("SHARED_STATE_REMOTE_ROOT", "/home/snh48_web")
SHARED_STATE_REMOTE_PYTHON = os.getenv(
    "SHARED_STATE_REMOTE_PYTHON", "/home/snh48_web/venv/bin/python"
)
SHARED_STATE_HISTORY_ROOT = os.getenv(
    "SHARED_STATE_HISTORY_ROOT",
    str(PROJECT_ROOT / "website" / "data" / "shared_state_history"),
)
SHARED_STATE_OUTBOX_ROOT = os.getenv(
    "SHARED_STATE_OUTBOX_ROOT",
    str(PROJECT_ROOT / "website" / "data" / "shared_state_outbox"),
)
ACTION_INBOX_ROOT = os.getenv(
    "ACTION_INBOX_ROOT",
    str(PROJECT_ROOT / "website" / "data" / "action_inbox"),
)
SHARED_STATE_NODE_LABELS = {
    "tencent": "腾讯云 cjy.plus",
    "aliyun": "阿里云 cjy.我爱你",
}

# 远程弹幕兜底读取。默认只硬拦截危险地址，域名白名单先用于灰度观察；
# 确认历史弹幕源都覆盖后再开启 DANMU_REMOTE_ENFORCE_HOST_ALLOWLIST=true。
DANMU_REMOTE_TIMEOUT_SECONDS = int(os.getenv("DANMU_REMOTE_TIMEOUT_SECONDS", "15"))
DANMU_REMOTE_MAX_BYTES = int(os.getenv("DANMU_REMOTE_MAX_BYTES", str(20 * 1024 * 1024)))
DANMU_REMOTE_ALLOWED_HOSTS = tuple(
    item.strip().lower()
    for item in os.getenv("DANMU_REMOTE_ALLOWED_HOSTS", "").split(",")
    if item.strip()
)
DANMU_REMOTE_ENFORCE_HOST_ALLOWLIST = os.getenv(
    "DANMU_REMOTE_ENFORCE_HOST_ALLOWLIST", "false"
).lower() in ("1", "true", "yes")
DANMU_REMOTE_CACHE_DIR = os.getenv("DANMU_REMOTE_CACHE_DIR", "")

# ── Event/Schedule CSV (事件/行程，由 fan-hub Codex 流程维护) ──────────────
# 主文件：/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv
EVENTS_CSV_PATH = os.getenv(
    "EVENTS_CSV_PATH",
    str(PROJECT_ROOT.parent / "snh48-fan-hub" / "schedule_record" / "chenjiayi_events.csv"),
)
# 兼容副本：/home/snh48-fan-hub/schedule_record/schedule.csv
SCHEDULE_CSV_PATH = os.getenv(
    "SCHEDULE_CSV_PATH",
    str(PROJECT_ROOT.parent / "snh48-fan-hub" / "schedule_record" / "schedule.csv"),
)

# ── Manual Events CSV (手动事件，修改后无需重启即可生效) ─────────────────
MANUAL_EVENTS_CSV_PATH = os.getenv(
    "MANUAL_EVENTS_CSV_PATH",
    str(WEBSITE_DIR / "data" / "manual_events.csv"),
)

# ── 出道整百天庆祝 ────────────────────────────────────────────────────────
# 第 300 天是整百天计算基准；此后每隔指定天数自动生成永久飘屏和时光轴事件。
DEBUT_300_DATE = os.getenv("DEBUT_300_DATE", "2026-07-31").strip() or "2026-07-31"
DEBUT_300_TEST_DATE = os.getenv("DEBUT_300_TEST_DATE", "").strip()
DEBUT_MILESTONE_INTERVAL_DAYS = max(1, int(os.getenv("DEBUT_MILESTONE_INTERVAL_DAYS", "100")))
# 7 表示里程碑当天至第 7 天（含）显示动画，共 8 个自然日。
DEBUT_CELEBRATION_DAYS_AFTER = max(0, int(os.getenv("DEBUT_CELEBRATION_DAYS_AFTER", "7")))

# ── JS Obfuscation ──────────────────────────────────────────────────────────
# 设置为 "true" 时使用混淆后的 JS（static/js-dist/），否则使用源文件（static/js/）
USE_OBFUSCATED_JS = os.getenv("USE_OBFUSCATED_JS", "").lower() in ("1", "true", "yes")
JS_DIST_DIR = STATIC_DIR / "js-dist" if USE_OBFUSCATED_JS else STATIC_DIR / "js"

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

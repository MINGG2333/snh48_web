"""
User Behavior Event Tracking Module

Records all user browsing and interaction events on the website, including:
  - Page visits (which page, when, referrer)
  - Button clicks (what was clicked)
  - Q&A interactions (question asked, answer received)
  - Form submissions (email, complaint, etc.)
  - Any other custom events

Outputs:
  1. user_events.jsonl  — 机器可读的 JSONL 日志（每行一个事件）
  2. user_events.md     — 人类可读的 Markdown 汇总文件（按时间倒序排列）
  3. notification_center.md — 统一通知中心（汇总所有待处理事件，含处理状态）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ── Event Types ────────────────────────────────────────────────────────────

EVENT_TYPES = {
    "page_view": "📄 页面浏览",
    "qa_submit": "🤖 问答提交",
    "qa_complete": "🤖 问答完成",
    "qa_timeout": "🤖 问答超时",
    "email_submit": "📧 邮箱提交",
    "complaint_submit": "📋 投诉提交",
    "login_attempt": "🔑 登录尝试",
    "click": "👆 点击事件",
    "screenshot": "📸 截图保存",
    "other": "❓ 其他事件",
}


def get_event_type_label(event_type: str) -> str:
    """Get the human-readable label for an event type."""
    return EVENT_TYPES.get(event_type, f"❓ {event_type}")


# ── Event Recording ────────────────────────────────────────────────────────


def record_user_event(
    session_dir: Path,
    client_id: str,
    event_type: str,
    event_data: dict[str, Any],
    *,
    push_to_notification: bool = False,
) -> None:
    """
    Record a user behavior event.

    Args:
        session_dir: The session log directory (from get_session_dir())
        client_id: The client identifier (from X-Client-Id header or generated)
        event_type: One of the EVENT_TYPES keys
        event_data: Arbitrary event data dict
        push_to_notification: If True, also push to notification_center.md
    """
    timestamp = datetime.now().isoformat()
    time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    record = {
        "client_id": client_id,
        "event_type": event_type,
        "event_type_label": get_event_type_label(event_type),
        "timestamp": timestamp,
        "time_str": time_str,
        "data": event_data,
    }

    # 1. Write to JSONL (machine-readable)
    jsonl_path = session_dir / "user_events.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 2. Write to Markdown (human-readable)
    md_path = session_dir / "user_events.md"
    md_entry = _build_md_entry(record)
    _prepend_to_file(md_path, md_entry)

    # 3. Optionally push to notification center
    if push_to_notification:
        _push_to_notification_center(session_dir, record)


def _build_md_entry(record: dict[str, Any]) -> str:
    """Build a Markdown entry for a user event record."""
    event_type_label = record["event_type_label"]
    time_str = record["time_str"]
    client_id = record["client_id"]
    data = record["data"]

    # Generate a short event ID
    ts = datetime.fromisoformat(record["timestamp"])
    event_id = f"EVT-{ts.strftime('%Y%m%d-%H%M%S')}-{client_id[:6]}"

    lines = [
        f"---\n",
        f"### {event_id}\n\n",
        f"| 字段 | 内容 |\n",
        f"|------|------|\n",
        f"| **时间** | {time_str} |\n",
        f"| **类型** | {event_type_label} |\n",
        f"| **用户** | `{client_id}` |\n",
    ]

    # Add event-specific fields
    page = data.get("page", "")
    if page:
        lines.append(f"| **页面** | `{page}` |\n")

    question = data.get("question", "")
    if question:
        lines.append(f"| **问题** | {question} |\n")

    answer_preview = data.get("answer_preview", "")
    if answer_preview:
        lines.append(f"| **答复摘要** | {answer_preview[:100]} |\n")

    email = data.get("email", "")
    if email:
        lines.append(f"| **邮箱** | `{email}` |\n")

    action = data.get("action", "")
    if action:
        lines.append(f"| **操作** | {action} |\n")

    detail = data.get("detail", "")
    if detail:
        lines.append(f"| **详情** | {detail} |\n")

    # Add reference to JSONL for machine-readable data
    lines.append(f"| **机器日志** | `user_events.jsonl` |\n")
    lines.append("\n")

    return "".join(lines)


def _push_to_notification_center(session_dir: Path, record: dict[str, Any]) -> None:
    """Push an event to the notification center."""
    notification_path = session_dir / "notification_center.md"
    event_type_label = record["event_type_label"]
    time_str = record["time_str"]
    client_id = record["client_id"]
    data = record["data"]

    ts = datetime.fromisoformat(record["timestamp"])
    event_id = f"EVT-{ts.strftime('%Y%m%d-%H%M%S')}-{client_id[:6]}"

    lines = [
        f"---\n",
        f"### {event_id}\n\n",
        f"| 字段 | 内容 |\n",
        f"|------|------|\n",
        f"| **时间** | {time_str} |\n",
        f"| **类型** | {event_type_label} |\n",
        f"| **用户** | `{client_id}` |\n",
    ]

    page = data.get("page", "")
    if page:
        lines.append(f"| **页面** | `{page}` |\n")

    question = data.get("question", "")
    if question:
        lines.append(f"| **问题** | {question} |\n")

    answer_preview = data.get("answer_preview", "")
    if answer_preview:
        lines.append(f"| **答复摘要** | {answer_preview[:100]} |\n")

    email = data.get("email", "")
    if email:
        lines.append(f"| **邮箱** | `{email}` |\n")

    action = data.get("action", "")
    if action:
        lines.append(f"| **操作** | {action} |\n")

    detail = data.get("detail", "")
    if detail:
        lines.append(f"| **详情** | {detail} |\n")

    lines.append(f"| **处理状态** | ⏳ 待处理 |\n")
    lines.append(f"| **处理备注** | |\n")
    lines.append("\n")

    entry = "".join(lines)

    # Prepend to notification center
    existing = ""
    if notification_path.exists():
        existing = notification_path.read_text(encoding="utf-8")

    with open(notification_path, "w", encoding="utf-8") as f:
        f.write("# 🔔 通知中心\n\n")
        f.write("> 所有需要管理员关注的事件汇总。按时间倒序排列，请及时处理。\n\n")
        f.write("## 待处理事件\n\n")
        f.write(entry)
        f.write(existing)


def _prepend_to_file(path: Path, entry: str) -> None:
    """Prepend an entry to a file (newest first)."""
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")

    with open(path, "w", encoding="utf-8") as f:
        f.write(entry)
        f.write(existing)

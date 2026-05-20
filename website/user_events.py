"""
User Behavior Event Tracking Module

Records all user browsing and interaction events on the website, including:
  - Page visits (which page, when, referrer)
  - Button clicks (what was clicked)
  - Q&A interactions (question asked, answer received)
  - Form submissions (email, complaint, etc.)
  - Any other custom events

Outputs:
  1. user_events.jsonl              — 所有用户混合的机器可读 JSONL 日志
  2. user_{client_id}_events.jsonl  — 按用户分开的机器可读 JSONL 日志
  3. user_{client_id}_events.md     — 按用户分开的人类可读 Markdown 汇总
  4. notification_center.md         — 统一通知中心（汇总所有待处理事件，含处理状态）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ── Event Types ────────────────────────────────────────────────────────────

EVENT_TYPES = {
    "page_view": "📄 页面浏览",
    "new_user": "🆕 新用户登入",
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

    Writes to:
      1. user_events.jsonl              — 所有用户混合的机器可读日志
      2. user_{client_id}_events.jsonl  — 按用户分开的机器可读日志
      3. user_{client_id}_events.md     — 按用户分开的人类可读 Markdown 汇总
      4. notification_center.md         — 重要事件的通知中心（可选）

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

    # 1. Write to combined JSONL (all users mixed, machine-readable)
    jsonl_path = session_dir / "user_events.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 2. Write to per-user JSONL (one file per user, machine-readable)
    user_jsonl_path = session_dir / f"user_{client_id}_events.jsonl"
    with open(user_jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 3. Write to per-user Markdown (one file per user, human-readable)
    #    Appended chronologically (oldest first, newest last)
    user_md_path = session_dir / f"user_{client_id}_events.md"
    md_entry = _build_md_entry(record)
    _append_to_file(user_md_path, md_entry)

    # 4. Optionally push to notification center
    if push_to_notification:
        _push_to_notification_center(session_dir, record)


def _build_md_entry(record: dict[str, Any]) -> str:
    """Build a Markdown table row for a user event record.

    Returns a single table row (without header) for chronological listing.
    """
    event_type_label = record["event_type_label"]
    time_str = record["time_str"]
    client_id = record["client_id"]
    data = record["data"]

    # Build the "内容" column with event details
    details = []

    page = data.get("page", "")
    if page:
        details.append(f"页面：`{page}`")

    question = data.get("question", "")
    if question:
        # Escape pipe characters to avoid breaking markdown table columns
        safe_question = question.replace("|", "\\|")
        details.append(f"问题：{safe_question}")

    answer_preview = data.get("answer_preview", "")
    if answer_preview:
        # Escape pipe characters to avoid breaking markdown table columns
        safe_preview = answer_preview[:100].replace("|", "\\|")
        details.append(f"答复摘要：{safe_preview}")

    email = data.get("email", "")
    if email:
        details.append(f"邮箱：`{email}`")

    action = data.get("action", "")
    if action:
        details.append(f"操作：{action}")

    # Show ticket_id for complaint submissions
    ticket_id = data.get("ticket_id", "")
    if ticket_id:
        details.append(f"受理编号：`{ticket_id}`")

    # Show complaint_type for complaint submissions
    complaint_type = data.get("complaint_type", "")
    if complaint_type:
        details.append(f"投诉类型：{complaint_type}")

    detail = data.get("detail", "")
    if detail:
        # Convert file references to Markdown links
        import re
        detail = re.sub(
            r'`(user_[a-zA-Z0-9_]+_events\.md)`',
            r'[\1](\1)',
            detail
        )
        details.append(f"详情：{detail}")

    # Use arrow separator to avoid breaking markdown table columns
    # The " | " separator would create additional columns in the table
    content = " → ".join(details) if details else "-"

    # ── Build "操作记录" column: identifier → [file_link] ──
    # Keep it simple: just a key identifier + markdown link to the file,
    # so you can search for the identifier in the linked file to locate the record.
    event_type = record["event_type"]
    action_col = "-"

    if event_type == "complaint_submit":
        ticket_id = data.get("ticket_id", "")
        complaint_file = data.get("complaint_file", "")
        if ticket_id and complaint_file:
            display_name = Path(complaint_file).name
            rel_path = "../complaints/" + display_name
            action_col = f"`{ticket_id}` → [{display_name}]({rel_path})"
        elif complaint_file:
            display_name = Path(complaint_file).name
            rel_path = "../complaints/" + display_name
            action_col = f"[{display_name}]({rel_path})"

    elif event_type == "email_submit":
        # Generate a unique event_id from timestamp + email/client_id
        # This matches the format used in email_requests.md (事件ID field)
        # and ensures each entry can be uniquely identified even if multiple
        # users send the same type of request.
        ts = datetime.fromisoformat(record["timestamp"])
        email_val = data.get("email", "")
        id_prefix = email_val[:6] if email_val else client_id[:6]
        event_id = f"EVT-{ts.strftime('%Y%m%d-%H%M%S')}-{id_prefix}"
        action_col = f"`{event_id}` → [email_requests.md](email_requests.md)"

    elif event_type in ("qa_complete", "qa_submit"):
        archive_path = data.get("archive_path", "")
        if archive_path:
            archive_name = Path(archive_path).name
            action_col = f"`{archive_name}` → [{archive_path}]({archive_path})"

    return f"| {time_str} | {event_type_label} | `{client_id}` | {content} | {action_col} |\n"


# ── Notification Center Usage Guide ────────────────────────────────────────

NOTIFICATION_USAGE_GUIDE = """\
## 📋 使用说明

### 通知中心是什么？
通知中心是网站所有**需要管理员关注的事件**的统一汇总页面。当用户进行以下操作时，会自动生成一条通知：
- 🆕 **新用户登入**（new_user）— 新用户首次访问网站
- 🤖 **提交问答**（qa_submit）— 用户向 AI 提问
- 🤖 **问答完成**（qa_complete）— AI 返回了回答
- 🤖 **问答超时**（qa_timeout）— 问题处理超时
- 📧 **提交邮箱**（email_submit）— 用户留下邮箱等待结果
- 📋 **提交投诉**（complaint_submit）— 用户提交投诉举报
- 🔑 **登录尝试**（login_attempt）— 用户尝试登录（含成功/失败）
- 📸 **截图保存**（screenshot）— 用户保存了问答截图

### 如何处理通知？

每条通知包含以下字段：

| 字段 | 说明 |
|------|------|
| **时间** | 事件发生的具体时间 |
| **类型** | 事件类型（见上方列表） |
| **用户** | 用户的唯一标识符（`client_id`） |
| **页面** | 事件发生的页面路径 |
| **问题** | 用户提出的问题内容 |
| **答复摘要** | AI 回答的摘要（前 100 字） |
| **邮箱** | 用户留下的联系邮箱 |
| **操作** | 具体操作描述 |
| **详情** | 补充信息 |
| **处理状态** | ⏳ 待处理 / ✅ 已处理 / ❌ 已忽略 |
| **处理备注** | 管理员填写的处理备注 |

### 处理流程

1. **查看通知** — 浏览通知列表，了解需要处理的事件
2. **标记状态** — 将 `处理状态` 从 `⏳ 待处理` 改为 `✅ 已处理` 或 `❌ 已忽略`
3. **填写备注** — 在 `处理备注` 中记录处理结果或说明
4. **处理邮箱请求** — 如果用户留下了邮箱，请及时回复
5. **处理投诉** — 投诉事件请参考 `complaints/` 目录下的详细投诉记录

### 关联文件

| 文件 | 说明 |
|------|------|
| `user_events.jsonl` | 所有事件的机器可读日志（JSONL 格式，每行一个事件） |
| `user_events.md` | 所有事件的人类可读汇总（含页面浏览等非通知事件） |
| `notification_center.md` | **本文件**，仅包含需要处理的重要事件 |
| `email_requests.md` | 用户邮箱请求汇总（由 qa_api 生成） |
| `complaints/` | 投诉记录目录（由 complaint_api 生成） |

> 💡 **提示：** 建议每天查看一次通知中心，及时处理用户请求和投诉。
"""


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
        safe_q = question.replace("|", "\\|")
        lines.append(f"| **问题** | {safe_q} |\n")

    answer_preview = data.get("answer_preview", "")
    if answer_preview:
        safe_a = answer_preview[:100].replace("|", "\\|")
        lines.append(f"| **答复摘要** | {safe_a} |\n")

    email = data.get("email", "")
    if email:
        lines.append(f"| **邮箱** | `{email}` |\n")

    action = data.get("action", "")
    if action:
        safe_act = action.replace("|", "\\|")
        lines.append(f"| **操作** | {safe_act} |\n")

    detail = data.get("detail", "")
    if detail:
        # Convert file references to Markdown links
        import re
        detail = re.sub(
            r'`(user_[a-zA-Z0-9_]+_events\.md)`',
            r'[\1](\1)',
            detail
        )
        lines.append(f"| **详情** | {detail} |\n")

    # Add link to user event file
    user_events_link = f"[user_{client_id}_events.md](user_{client_id}_events.md)"
    lines.append(f"| **用户操作记录** | {user_events_link} |\n")
    lines.append(f"| **处理状态** | ⏳ 待处理 |\n")
    lines.append(f"| **处理备注** | |\n")
    lines.append("\n")

    entry = "".join(lines)

    # ── 1. Write to per-session notification center ──
    if notification_path.exists():
        # File exists — insert new entry after "## 待处理事件" header
        existing = notification_path.read_text(encoding="utf-8")
        # Find the "## 待处理事件" section and insert after it
        marker = "## 待处理事件\n\n"
        marker_pos = existing.find(marker)
        if marker_pos != -1:
            after_marker = marker_pos + len(marker)
            before = existing[:after_marker]
            after = existing[after_marker:]
            with open(notification_path, "w", encoding="utf-8") as f:
                f.write(before)
                f.write(entry)
                f.write(after)
        else:
            # Fallback: prepend to beginning
            with open(notification_path, "w", encoding="utf-8") as f:
                f.write(entry)
                f.write(existing)
    else:
        # First event — create file with header
        with open(notification_path, "w", encoding="utf-8") as f:
            f.write("# 🔔 通知中心\n\n")
            f.write("> 所有需要管理员关注的事件汇总。按时间倒序排列，请及时处理。\n\n")
            f.write("## 待处理事件\n\n")
            f.write(entry)

    # ── 2. Write to global notification center (across all sessions) ──
    _push_to_global_notification_center(session_dir, record, entry)


def _push_to_global_notification_center(
    session_dir: Path, record: dict[str, Any], entry: str
) -> None:
    """Push an event to the global notification center (across all sessions).

    The global notification center lives at ``interaction_logs/_all_notifications.md``.
    It organizes notifications by session, with the newest session first.
    Within each session section, events are listed newest first.
    """
    global_path = session_dir.parent / "_all_notifications.md"
    session_name = session_dir.name  # e.g. "session_20260521_033000"
    session_start_time = session_name.replace("session_", "")

    # ── Parse existing file into session blocks ──
    # Each block is a dict: {"session": str, "start_time": str, "events": [str]}
    # Blocks are ordered newest session first.
    blocks: list[dict] = []

    if global_path.exists():
        raw = global_path.read_text(encoding="utf-8")
        # Split by session headers (## 📁 session_...)
        parts = raw.split("\n## 📁 ")
        for part in parts[1:]:  # Skip the header part (before first session)
            lines = part.split("\n")
            sess_name = lines[0].strip()
            # Find start time
            start_time = ""
            events_start = 0
            for i, line in enumerate(lines[1:], 1):
                if line.startswith("> 会话启动时间："):
                    start_time = line.replace("> 会话启动时间：", "").strip()
                elif line.startswith("### "):
                    events_start = i
                    break
            # Collect all events (### ... --- ...)
            events_text = "\n".join(lines[events_start:]) if events_start > 0 else ""
            blocks.append({
                "session": sess_name,
                "start_time": start_time,
                "events": events_text,
            })

    # ── Find or create the block for this session ──
    target_block = None
    for block in blocks:
        if block["session"] == session_name:
            target_block = block
            break

    if target_block is None:
        # New session — insert at the beginning (newest first)
        blocks.insert(0, {
            "session": session_name,
            "start_time": session_start_time,
            "events": "",
        })
        target_block = blocks[0]

    # ── Build the global event entry directly from record (not from per-session entry) ──
    # This avoids duplicating the per-session notification format (---, ### EVT-..., etc.)
    event_type_label = record["event_type_label"]
    time_str = record["time_str"]
    client_id = record["client_id"]
    data = record["data"]

    ts = datetime.fromisoformat(record["timestamp"])
    event_id = f"EVT-{ts.strftime('%Y%m%d-%H%M%S')}-{client_id[:6]}"

    global_lines = [
        f"### {event_type_label}\n\n",
        f"| 字段 | 内容 |\n",
        f"|------|------|\n",
        f"| **事件ID** | {event_id} |\n",
        f"| **时间** | {time_str} |\n",
        f"| **类型** | {event_type_label} |\n",
        f"| **用户** | `{client_id}` |\n",
    ]

    page = data.get("page", "")
    if page:
        global_lines.append(f"| **页面** | `{page}` |\n")

    question = data.get("question", "")
    if question:
        safe_q = question.replace("|", "\\|")
        global_lines.append(f"| **问题** | {safe_q} |\n")

    answer_preview = data.get("answer_preview", "")
    if answer_preview:
        safe_a = answer_preview[:100].replace("|", "\\|")
        global_lines.append(f"| **答复摘要** | {safe_a} |\n")

    email = data.get("email", "")
    if email:
        global_lines.append(f"| **邮箱** | `{email}` |\n")

    action = data.get("action", "")
    if action:
        safe_act = action.replace("|", "\\|")
        global_lines.append(f"| **操作** | {safe_act} |\n")

    detail = data.get("detail", "")
    if detail:
        import re
        detail = re.sub(
            r'`(user_[a-zA-Z0-9_]+_events\.md)`',
            r'[\1](\1)',
            detail
        )
        global_lines.append(f"| **详情** | {detail} |\n")

    user_events_link = f"[user_{client_id}_events.md](user_{client_id}_events.md)"
    global_lines.append(f"| **用户操作记录** | {user_events_link} |\n")
    global_lines.append(f"| **处理状态** | ⏳ 待处理 |\n")
    global_lines.append(f"| **处理备注** | |\n")
    global_lines.append("\n")

    new_event = "".join(global_lines)

    # ── Prepend the new event to the session's events ──
    if target_block["events"]:
        target_block["events"] = new_event + "\n" + target_block["events"]
    else:
        target_block["events"] = new_event

    # ── Write the file ──
    with open(global_path, "w", encoding="utf-8") as f:
        f.write("# 📋 总通知中心\n\n")
        f.write("> 所有会话的通知汇总。按会话倒序排列（最新会话在上），每个会话内按时间倒序排列。\n\n")

        # Table of contents — link to each session's notification_center.md
        f.write("## 目录\n\n")
        f.write("| 会话 | 启动时间 | 通知中心 |\n")
        f.write("|------|----------|----------|\n")
        for block in blocks:
            sess_dir_name = block["session"]
            nc_link = f"[notification_center.md]({sess_dir_name}/notification_center.md)"
            f.write(f"| {block['session']} | {block['start_time']} | {nc_link} |\n")
        f.write("\n---\n\n")

        # Session blocks
        for block in blocks:
            sess_dir_name = block["session"]
            nc_link = f"[notification_center.md]({sess_dir_name}/notification_center.md)"
            f.write(f"## 📁 {block['session']}\n\n")
            f.write(f"> 会话启动时间：{block['start_time']} — 查看完整通知：{nc_link}\n\n")
            # Fix detail links in events: they are relative to session dir,
            # but in global file they need to be prefixed with session dir name
            events_fixed = block["events"]
            import re
            events_fixed = re.sub(
                r'(\[user_[a-zA-Z0-9_]+_events\.md\]\()(user_[a-zA-Z0-9_]+_events\.md)\)',
                lambda m: f"{m.group(1)}{sess_dir_name}/{m.group(2)})",
                events_fixed
            )
            f.write(events_fixed)
            f.write("\n\n---\n\n")


def _append_to_file(path: Path, entry: str) -> None:
    """Append an entry to a file (chronological order, oldest first).

    If the file doesn't exist yet, creates it with a table header first.
    """
    if not path.exists():
        # Create file with table header
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 📋 用户操作记录\n\n")
            f.write("| 时间 | 类型 | 用户 | 内容 | 操作记录 |\n")
            f.write("|------|------|------|------|----------|\n")

    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def _prepend_to_file(path: Path, entry: str) -> None:
    """Prepend an entry to a file (newest first)."""
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")

    with open(path, "w", encoding="utf-8") as f:
        f.write(entry)
        f.write(existing)

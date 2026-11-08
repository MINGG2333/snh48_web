"""转录纠错词表的网站侧存储。

网站页面提交的纠错写入项目可写的 web_state 目录，worker 会定时合并并应用。
文件只保存“错误词 -> 正确词”，不保存音频或完整转录，不进入 Git。
"""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = Path(
    os.getenv(
        "ASR_CORRECTIONS_PATH",
        str(PROJECT_ROOT.parent / "snh48-fan-hub" / "private_handover" / "web_state" / "asr_corrections.json"),
    )
)
BJ_TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": []}
    if not isinstance(data, dict):
        return {"version": 1, "entries": []}
    data.setdefault("entries", [])
    return data


def add(wrong: str, right: str, *, context: str = "", by: str = "website") -> dict:
    wrong = str(wrong or "").strip()
    right = str(right or "").strip()
    if not wrong or not right:
        raise ValueError("错误词和正确词都不能为空")
    if len(wrong) > 40 or len(right) > 40:
        raise ValueError("词条长度不能超过 40")
    if wrong == right:
        raise ValueError("错误词和正确词相同")

    path = DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _load(path)
        entries = data.setdefault("entries", [])
        entry = next((item for item in entries if item.get("wrong") == wrong), None)
        if entry is None:
            entry = {
                "id": "w-" + uuid.uuid4().hex[:8],
                "wrong": wrong,
                "right": right,
                "note": str(context or "")[:200],
                "created_at": _now(),
                "created_by": by,
            }
            entries.append(entry)
        else:
            entry.update({"right": right, "note": str(context or "")[:200], "updated_at": _now(), "updated_by": by})
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o664)
        tmp.replace(path)
        fcntl.flock(lock, fcntl.LOCK_UN)
    return entry

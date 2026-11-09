#!/usr/bin/env python3
"""汇总网站用户操作日志。

读取：
  website/data/interaction_logs/session_*/user_events.jsonl
  <fan-hub>/private_handover/web_state/audit/user_actions-YYYYMM.jsonl

用法：
  script/user_activity_report.py --days 7
  script/user_activity_report.py --date 2026-11-09 --json
  script/user_activity_report.py --days 30 --client user_xxx
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = PROJECT_ROOT / "website" / "data" / "interaction_logs"
AUDIT_DIR = Path(
    os.getenv(
        "USER_AUDIT_DIR",
        str(PROJECT_ROOT.parent / "snh48-fan-hub" / "private_handover" / "web_state" / "audit"),
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--date", default="")
    parser.add_argument("--client", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def iter_events() -> list[dict]:
    events: list[dict] = []
    for path in glob.glob(str(LOG_ROOT / "session_*" / "user_events.jsonl")):
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def iter_audit() -> list[dict]:
    rows: list[dict] = []
    for path in glob.glob(str(AUDIT_DIR / "user_actions-*.jsonl")):
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def event_time(event: dict) -> datetime | None:
    value = str(event.get("timestamp") or event.get("time_str") or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:26], fmt)
        except ValueError:
            continue
    return None


def main() -> int:
    args = parse_args()
    if args.date:
        start = datetime.strptime(args.date, "%Y-%m-%d")
        end = start + timedelta(days=1)
    else:
        end = datetime.now() + timedelta(seconds=1)
        start = end - timedelta(days=max(1, args.days))

    events = []
    for event in iter_events():
        ts = event_time(event)
        if ts is None or not (start <= ts < end):
            continue
        if args.client and event.get("client_id") != args.client:
            continue
        events.append(event)
    audit = []
    for row in iter_audit():
        try:
            ts = datetime.strptime(str(row.get("ts")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if start <= ts < end:
            audit.append(row)

    type_counts = collections.Counter(str(e.get("event_type") or "other") for e in events)
    page_counts = collections.Counter(str((e.get("data") or {}).get("page") or "") for e in events)
    action_counts = collections.Counter(
        str((e.get("data") or {}).get("action") or "") for e in events if (e.get("data") or {}).get("action")
    )
    clients = collections.Counter(str(e.get("client_id") or "") for e in events)
    audit_paths = collections.Counter(f"{r.get('method')} {r.get('path')} -> {r.get('status')}" for r in audit)

    if args.json:
        print(json.dumps(
            {
                "range": [start.strftime("%F %T"), end.strftime("%F %T")],
                "events": len(events),
                "unique_clients": len(clients),
                "by_type": type_counts.most_common(),
                "by_page": page_counts.most_common(20),
                "top_actions": action_counts.most_common(20),
                "audit_writes": audit_paths.most_common(20),
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    print(f"范围：{start:%F %T} ~ {end:%F %T}")
    print(f"事件数：{len(events)}，独立 client：{len(clients)}，写操作审计：{len(audit)}")
    print("\n事件类型：")
    for name, count in type_counts.most_common(15):
        print(f"  {name}: {count}")
    print("\n页面：")
    for name, count in page_counts.most_common(10):
        if name:
            print(f"  {name}: {count}")
    print("\n高频动作：")
    for name, count in action_counts.most_common(15):
        print(f"  {name}: {count}")
    if audit_paths:
        print("\n写操作：")
        for name, count in audit_paths.most_common(15):
            print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

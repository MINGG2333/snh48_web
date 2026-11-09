#!/usr/bin/env python3
"""把过期的用户操作日志和审计记录打包归档（只复制，不删除源文件）。

默认 dry-run；需要显式 --dest 才会写出 tar.gz 和 manifest。不会自动删除源目录，
符合“保留期不等于永久删除”的策略。

用法：
  script/archive_user_activity.py --before 2026-06-01 --dest /mnt/nas-backup/snh48-web-logs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = PROJECT_ROOT / "website" / "data" / "interaction_logs"
AUDIT_DIR = PROJECT_ROOT.parent / "snh48-fan-hub" / "private_handover" / "web_state" / "audit"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def session_day(path: Path) -> datetime | None:
    name = path.name
    if not name.startswith("session_"):
        return None
    try:
        return datetime.strptime(name[len("session_"):][:8], "%Y%m%d")
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, help="YYYY-MM-DD，早于该日期的数据进入归档")
    parser.add_argument("--dest", default="", help="归档输出目录；为空时只列出将要归档的内容")
    args = parser.parse_args()
    cutoff = parse_day(args.before)

    sessions = [p for p in LOG_ROOT.glob("session_*") if p.is_dir() and (d := session_day(p)) and d < cutoff]
    audit_files = [p for p in AUDIT_DIR.glob("user_actions-*.jsonl") if p.is_file()]

    total = sum(f.stat().st_size for d in sessions for f in d.rglob("*") if f.is_file())
    total += sum(f.stat().st_size for f in audit_files)
    print(f"cutoff={cutoff:%F} sessions={len(sessions)} audit_files={len(audit_files)} bytes={total}")
    for d in sessions:
        print("  session", d.name)
    for f in audit_files:
        print("  audit", f.name)

    if not args.dest:
        print("dry-run：未指定 --dest，不写归档")
        return 0
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = dest / f"snh48-web-logs-{stamp}.tar.gz"
    manifest = {"created_at": datetime.now().isoformat(), "cutoff": args.before, "files": []}
    with tarfile.open(archive_path, "w:gz") as tar:
        for d in sessions:
            tar.add(d, arcname=f"interaction_logs/{d.name}")
            for f in d.rglob("*"):
                if f.is_file():
                    manifest["files"].append({"path": f"interaction_logs/{d.relative_to(LOG_ROOT)}/{f.relative_to(d)}", "size": f.stat().st_size, "sha256": sha256(f)})
        for f in audit_files:
            tar.add(f, arcname=f"audit/{f.name}")
            manifest["files"].append({"path": f"audit/{f.name}", "size": f.stat().st_size, "sha256": sha256(f)})
    manifest_path = archive_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"归档完成：{archive_path}（{archive_path.stat().st_size} bytes）")
    print(f"manifest：{manifest_path}")
    print("源文件未删除；确认归档和校验后再人工清理。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

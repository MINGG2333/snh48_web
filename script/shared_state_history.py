#!/usr/bin/env python3
"""List or restore immutable shared runtime-state revisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from website.shared_runtime_state import ensure_baseline, list_history, replicate_current, restore_revision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("resource", choices=("scroller", "room_ignore", "score_business", "memories"))
    list_parser.add_argument("--limit", type=int, default=20)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("resource", choices=("scroller", "room_ignore", "score_business", "memories"))
    restore_parser.add_argument("revision")
    baseline_parser = sub.add_parser("baseline")
    baseline_parser.add_argument(
        "resource",
        choices=("all", "scroller", "room_ignore", "score_business", "memories"),
    )
    replicate_parser = sub.add_parser("replicate")
    replicate_parser.add_argument(
        "resource",
        choices=("scroller", "room_ignore", "score_business", "memories"),
    )
    args = parser.parse_args()

    if args.command == "list":
        print(json.dumps(list_history(args.resource, limit=args.limit), ensure_ascii=False, indent=2))
    elif args.command == "restore":
        print(json.dumps(restore_revision(args.resource, args.revision), ensure_ascii=False, indent=2))
    elif args.command == "baseline":
        resources = (
            ("scroller", "room_ignore", "score_business", "memories")
            if args.resource == "all"
            else (args.resource,)
        )
        result = {
            resource: (ensure_baseline(resource).get("_state") or {}).get("revision", "")
            for resource in resources
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"resource": args.resource, "replicated": replicate_current(args.resource)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

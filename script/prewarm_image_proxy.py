#!/usr/bin/env python3
"""
Prewarm the Nginx /image-proxy/ cache for recent sinaimg images.

Run this on the web server after schedule.csv is synced. It requests the
same public /image-proxy/ URLs that browsers use, so Nginx fills its shared
cache without changing the page runtime path.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_FIELDS = ("cover_url", "event_images", "image_urls")
DEFAULT_SCHEDULE_CSV = "/home/snh48-fan-hub/schedule_record/schedule.csv"
DEFAULT_BASE_URL = "https://cjy.plus"
READ_CHUNK_SIZE = 256 * 1024


def split_multi_urls(value: str) -> Iterable[str]:
    for item in (value or "").split(";"):
        item = item.strip()
        if item:
            yield item


def sinaimg_to_proxy_path(raw_url: str) -> Optional[str]:
    raw_url = (raw_url or "").strip()
    if raw_url.startswith("/image-proxy/"):
        return raw_url.split("?", 1)[0]

    parsed = urlsplit(raw_url)
    host = (parsed.hostname or "").lower()
    if not host.endswith("sinaimg.cn"):
        return None
    if not parsed.path.startswith("/"):
        return None
    return f"/image-proxy{parsed.path}"


def row_sort_key(row: Dict[str, str]) -> Tuple[str, str, str]:
    return (
        (row.get("date") or "").strip(),
        (row.get("time") or "").strip(),
        (row.get("updated_at") or "").strip(),
    )


def collect_proxy_paths(csv_path: Path, fields: Sequence[str], limit: int) -> List[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    rows.sort(key=row_sort_key, reverse=True)
    seen = set()
    result: List[str] = []
    for row in rows:
        for field in fields:
            for raw_url in split_multi_urls(row.get(field, "")):
                proxy_path = sinaimg_to_proxy_path(raw_url)
                if not proxy_path or proxy_path in seen:
                    continue
                seen.add(proxy_path)
                result.append(proxy_path)
                if len(result) >= limit:
                    return result
    return result


def normalize_base_url(base_url: str) -> str:
    base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if not base_url:
        return DEFAULT_BASE_URL
    if "://" not in base_url:
        return f"https://{base_url}"
    return base_url


def fetch_full_url(url: str, timeout: float, user_agent: str) -> Tuple[str, int, int, Optional[str]]:
    request = Request(url, headers={"User-Agent": user_agent})
    total = 0
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            while True:
                chunk = response.read(READ_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
            return url, status, total, None
    except HTTPError as exc:
        return url, exc.code, total, str(exc)
    except (OSError, URLError) as exc:
        return url, 0, total, str(exc)


def prewarm(urls: Sequence[str], workers: int, timeout: float, user_agent: str) -> int:
    failures = 0
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
        futures = [executor.submit(fetch_full_url, url, timeout, user_agent) for url in urls]
        for future in as_completed(futures):
            url, status, byte_count, error = future.result()
            if 200 <= status < 300:
                print(f"OK {status} {byte_count} {url}")
            else:
                failures += 1
                print(f"FAIL {status} {byte_count} {url} {error or ''}".rstrip(), file=sys.stderr)
    return failures


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prewarm /image-proxy/ cache from schedule.csv")
    parser.add_argument(
        "--schedule-csv",
        default=os.environ.get("SCHEDULE_CSV_PATH", DEFAULT_SCHEDULE_CSV),
        help="schedule.csv path",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("IMAGE_PROXY_BASE_URL") or os.environ.get("SITE_DOMAIN") or DEFAULT_BASE_URL,
        help="public site base URL, for example https://cjy.plus",
    )
    parser.add_argument("--limit", type=int, default=120, help="maximum unique sinaimg URLs to prewarm")
    parser.add_argument("--workers", type=int, default=8, help="parallel request workers")
    parser.add_argument("--timeout", type=float, default=20.0, help="per-image request timeout seconds")
    parser.add_argument(
        "--field",
        action="append",
        dest="fields",
        help="CSV field to read; can be repeated. Defaults to cover_url, event_images, image_urls",
    )
    parser.add_argument("--dry-run", action="store_true", help="print URLs without requesting them")
    parser.add_argument(
        "--user-agent",
        default="snh48-web-image-prewarm/1.0",
        help="User-Agent used for prewarm requests",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    csv_path = Path(args.schedule_csv)
    if not csv_path.exists():
        print(f"schedule.csv not found: {csv_path}", file=sys.stderr)
        return 2

    fields = tuple(args.fields or DEFAULT_FIELDS)
    proxy_paths = collect_proxy_paths(csv_path, fields, max(args.limit, 0))
    base_url = normalize_base_url(args.base_url)
    urls = [f"{base_url}{path}" for path in proxy_paths]

    print(f"Found {len(urls)} image proxy URLs from {csv_path}")
    if args.dry_run:
        for url in urls:
            print(url)
        return 0

    failures = prewarm(urls, workers=args.workers, timeout=args.timeout, user_agent=args.user_agent)
    print(f"Done. success={len(urls) - failures} failure={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

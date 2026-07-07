#!/usr/bin/env python3
"""
Build initial memories data from snh48-fan-hub derived datasets.

The output file is runtime data and is intentionally ignored by Git:
website/data/memories/memories.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FAN_HUB = ROOT.parent / "snh48-fan-hub"
DEFAULT_OUTPUT = ROOT / "website" / "data" / "memories" / "memories.json"
MEMBER_DIR = "陈嘉仪_161808449"

MEMORY_TYPES = {
    "idol_reply": "小偶像回应粉丝",
    "fan_expression": "粉丝表达喜欢",
    "fan_work": "粉丝为她做的事",
    "shared_memory": "共同记忆",
    "private_interaction": "私密或半私密互动",
}

PLATFORMS = {
    "pocket48": "口袋48",
    "weibo": "微博",
    "bilibili": "B站",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "youtube": "YouTube",
    "fanclub": "应援会",
    "offline": "线下",
    "other": "其他",
}

PRESERVE_FIELDS = {
    "audit_status",
    "audit_reason",
    "visibility",
    "confirmation_status",
    "confirmed_by",
    "confirmed_at",
    "created_at",
    "last_reviewed_by",
    "last_reviewed_at",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build memories seed data.")
    parser.add_argument("--fan-hub", type=Path, default=DEFAULT_FAN_HUB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-date", default="2025-09-01")
    parser.add_argument("--gift-replies-limit", type=int, default=160)
    parser.add_argument("--live-gifts-limit", type=int, default=160)
    parser.add_argument("--events-limit", type=int, default=120)
    args = parser.parse_args()

    fan_hub = args.fan_hub
    generated: list[dict[str, Any]] = []
    generated.extend(build_gift_reply_memories(fan_hub, args.start_date, args.gift_replies_limit))
    generated.extend(build_live_gift_memories(fan_hub, args.start_date, args.live_gifts_limit))
    generated.extend(build_event_memories(fan_hub, args.start_date, args.events_limit))

    store = merge_with_existing(args.output, generated)
    write_store(args.output, store)
    print(
        f"Wrote {len(store.get('items', []))} memories to {args.output} "
        f"({len(generated)} generated/updated)"
    )
    return 0


def build_gift_reply_memories(fan_hub: Path, start_date: str, limit: int) -> list[dict[str, Any]]:
    path = fan_hub / "room_record" / MEMBER_DIR / "gift_replies" / "gifts.csv"
    rows = read_csv(path)
    output: list[dict[str, Any]] = []
    for row in rows:
        gift_time = row.get("gift_bj_time", "")
        if not _after_start(gift_time, start_date):
            continue
        if row.get("reply_status") != "replied":
            continue
        gift_name = row.get("gift_name", "礼物") or "礼物"
        sender = row.get("sender_name", "") or "一位粉丝"
        gift_count = row.get("gift_count", "") or "1"
        reply_text = row.get("first_reply_content") or row.get("latest_reply_content") or ""
        reply_type = row.get("first_reply_type") or row.get("latest_reply_type") or ""
        duration = row.get("first_reply_duration_seconds") or ""
        if not reply_text and "AUDIO" in reply_type:
            reply_text = f"语音回复{f' {duration} 秒' if duration else ''}"
        if not reply_text:
            reply_text = "收到了一次回复"
        occurred_at = row.get("first_reply_bj_time") or gift_time
        title = f"{sender} 的 {gift_name} 收到了回复"
        summary = f"{sender} 在口袋48房间送出 {gift_count} 个 {gift_name}，陈嘉仪回复：{reply_text}"
        output.append(base_record(
            source_kind="pocket48_room_gift_reply",
            source_parts=[row.get("gift_message_id", ""), row.get("first_reply_message_id", "")],
            memory_type="idol_reply",
            title=title,
            occurred_at=occurred_at,
            summary=summary,
            public_note="来自口袋48房间礼物与回礼物记录。",
            actor_display_name=sender,
            actor_platform="pocket48",
            actor_platform_id=row.get("sender_id", ""),
            source_label="口袋48房间礼物回复",
            source_url="",
            source_external_id=row.get("gift_message_id", ""),
            image_url=row.get("gift_icon_url", ""),
            tags=["口袋48", "房间礼物", "回复"],
        ))
        if len(output) >= limit:
            break
    return output


def build_live_gift_memories(fan_hub: Path, start_date: str, limit: int) -> list[dict[str, Any]]:
    path = fan_hub / "room_record" / MEMBER_DIR / "score_gifts" / "score_gifts.json"
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = doc.get("items", [])
    if not isinstance(items, list):
        return []
    output: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict) or row.get("source") != "live":
            continue
        event_time = str(row.get("event_time", ""))
        if not _after_start(event_time, start_date):
            continue
        sender = str(row.get("sender_name", "")) or "一位粉丝"
        gift_name = str(row.get("gift_name", "")) or "礼物"
        gift_count = str(row.get("gift_count", "") or "1")
        live_title = str(row.get("live_title", "")) or "一次直播"
        fulfillment = str(row.get("fulfillment_label", ""))
        summary = f"{sender} 在《{live_title}》中送出 {gift_count} 个 {gift_name}。"
        if fulfillment:
            summary += f" 这条记录的业务状态为：{fulfillment}。"
        output.append(base_record(
            source_kind="pocket48_live_score_gift",
            source_parts=[str(row.get("id", "")), str(row.get("live_id", ""))],
            memory_type="fan_expression",
            title=f"{sender} 在直播里留下了 {gift_name} 记忆",
            occurred_at=event_time,
            summary=summary,
            public_note="来自口袋48直播弹幕礼物记录。",
            actor_display_name=sender,
            actor_platform="pocket48",
            actor_platform_id=str(row.get("sender_id", "")),
            source_label="口袋48直播礼物",
            source_url="",
            source_external_id=str(row.get("id", "")),
            image_url=str(row.get("gift_icon_url", "")),
            tags=["口袋48", "直播礼物"],
        ))
        if len(output) >= limit:
            break
    return output


def build_event_memories(fan_hub: Path, start_date: str, limit: int) -> list[dict[str, Any]]:
    path = fan_hub / "schedule_record" / "chenjiayi_events.csv"
    rows = read_csv(path)
    output: list[dict[str, Any]] = []
    for row in rows:
        date_value = row.get("date", "")
        if not _after_start(date_value, start_date):
            continue
        title = row.get("name", "") or row.get("type", "") or "一条共同记忆"
        event_type = row.get("type", "")
        time_value = row.get("time", "")
        occurred_at = f"{date_value} {time_value}".strip()
        description = row.get("description", "") or title
        image_url = first_semicolon_value(row.get("image_urls", ""))
        source_url = row.get("source_url", "") or first_semicolon_value(row.get("snh48_weibo_urls", ""))
        output.append(base_record(
            source_kind="schedule_event",
            source_parts=[date_value, time_value, title, source_url],
            memory_type="shared_memory",
            title=title,
            occurred_at=occurred_at,
            summary=description,
            public_note="来自网站时光轴行程资料。",
            actor_display_name="",
            actor_platform="offline" if event_type else "other",
            actor_platform_id="",
            source_label="时光轴行程",
            source_url=source_url,
            source_external_id=row.get("source_msg_id", ""),
            image_url=image_url,
            tags=[item for item in [event_type, "共同记忆"] if item],
        ))
        if len(output) >= limit:
            break
    return output


def base_record(
    *,
    source_kind: str,
    source_parts: list[str],
    memory_type: str,
    title: str,
    occurred_at: str,
    summary: str,
    public_note: str,
    actor_display_name: str,
    actor_platform: str,
    actor_platform_id: str,
    source_label: str,
    source_url: str,
    source_external_id: str,
    image_url: str,
    tags: list[str],
) -> dict[str, Any]:
    now = now_iso()
    return {
        "id": stable_id(source_kind, source_parts),
        "memory_type": memory_type,
        "title": clean(title, 100),
        "occurred_at": clean(occurred_at, 32),
        "summary": clean(summary, 1200),
        "public_note": clean(public_note, 1200),
        "actor": {
            "display_name": clean(actor_display_name, 80),
            "platform": actor_platform if actor_platform in PLATFORMS else "other",
            "platform_label": PLATFORMS.get(actor_platform, "其他"),
            "platform_id": clean(actor_platform_id, 120),
        },
        "source": {
            "kind": source_kind,
            "label": source_label,
            "url": clean(source_url, 500),
            "external_id": clean(source_external_id, 160),
        },
        "media": {
            "image_url": clean(image_url, 500),
            "thumbnail_url": clean(image_url, 500),
        },
        "privacy_level": "public",
        "evidence_public": True,
        "tags": unique_tags(tags),
        "audit_status": "auto_approved",
        "audit_reason": "由 fan-hub 既有数据生成",
        "visibility": "public",
        "confirmation_status": "unconfirmed",
        "confirmed_by": "",
        "confirmed_at": "",
        "created_by": "system_seed",
        "created_at": now,
        "updated_at": now,
        "memory_type_label": MEMORY_TYPES.get(memory_type, memory_type),
    }


def merge_with_existing(output: Path, generated: list[dict[str, Any]]) -> dict[str, Any]:
    existing_items: list[dict[str, Any]] = []
    if output.exists():
        try:
            doc = json.loads(output.read_text(encoding="utf-8"))
            items = doc.get("items", [])
            if isinstance(items, list):
                existing_items = [item for item in items if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            existing_items = []

    by_id = {str(item.get("id", "")): item for item in existing_items if item.get("id")}
    for item in generated:
        old = by_id.get(item["id"])
        if old:
            for field in PRESERVE_FIELDS:
                if field in old:
                    item[field] = old[field]
            item["updated_at"] = now_iso()
        by_id[item["id"]] = item

    items = list(by_id.values())
    items.sort(key=lambda item: (str(item.get("occurred_at", "")), str(item.get("created_at", ""))), reverse=True)
    return {
        "version": 1,
        "updated_at": now_iso(),
        "items": items,
    }


def write_store(output: Path, store: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(store, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as f:
        f.write(content)
        tmp_name = f.name
    Path(tmp_name).replace(output)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def stable_id(source_kind: str, parts: list[str]) -> str:
    raw = source_kind + "\n" + "\n".join(str(part) for part in parts if part)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14].upper()
    return f"MEM-{digest}"


def first_semicolon_value(value: str) -> str:
    return next((part.strip() for part in str(value or "").split(";") if part.strip()), "")


def unique_tags(tags: list[str]) -> list[str]:
    output: list[str] = []
    for tag in tags:
        text = clean(tag, 20)
        if text and text not in output:
            output.append(text)
    return output[:8]


def clean(value: Any, max_length: int) -> str:
    text = str(value or "").strip().replace("\r", "\n")
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:max_length]


def _after_start(value: str, start_date: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 10:
        return False
    return text[:10] >= start_date


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())

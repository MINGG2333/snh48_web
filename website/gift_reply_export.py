"""礼物回复页 PNG 导出（Pillow 服务端渲染）。

两个版式与交接包手工图一致：
- 时间线：按天分组，最新在前，适合逐条查看；
- 回复情况：按送礼人聚合，两列卡片，红=待回、绿=已回。

只依赖 Pillow 与系统 CJK 字体（阿里云文泉驿/腾讯云 Noto 均可）。
"""
from __future__ import annotations

import datetime as dt
import io
import unicodedata
from functools import lru_cache
from typing import Any, Iterable

WIDTH = 1000
PAD = 24
SECTION_PAD = 20
CARD_GAP = 16
RADIUS = 14

BG = (247, 243, 251)
SECTION_BG = (255, 255, 255)
CARD_BG = (251, 249, 253)
CARD_BORDER = (236, 227, 245)
TITLE = (90, 61, 153)
SUBTITLE = (152, 133, 184)
TEXT = (51, 51, 51)
MUTED = (154, 145, 168)
FAINT = (168, 156, 192)
NAME = (74, 53, 96)
PINK = (192, 73, 122)
PINK_BG = (251, 227, 238)
GREEN = (45, 138, 110)
GREEN_BG = (228, 242, 234)
LINE = (229, 220, 240)
NOTE_BG = (244, 239, 252)
COUNT = (192, 73, 122)
COUNT_DONE = (127, 143, 134)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
BOLD_CANDIDATES = (
    "/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
) + FONT_CANDIDATES


def _pil():
    from PIL import Image, ImageDraw, ImageFont

    return Image, ImageDraw, ImageFont


@lru_cache(maxsize=256)
def _font(size: int, bold: bool = False):
    _, _, ImageFont = _pil()
    candidates = BOLD_CANDIDATES if bold else FONT_CANDIDATES
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _display_text(text: Any) -> str:
    """去掉 CJK 字体无法渲染的 emoji/补充平面字符，避免导出图出现方框。"""
    value = "" if text is None else str(text)
    cleaned = []
    for char in value:
        code = ord(char)
        if code in (0x200D, 0xFE0E, 0xFE0F) or 0x1F3FB <= code <= 0x1F3FF:
            continue
        if 0x02B0 <= code <= 0x02FF or 0x1D00 <= code <= 0x1DBF:
            continue
        if 0x2500 <= code <= 0x28FF:
            continue
        if unicodedata.category(char) in {"Mn", "Me", "So", "Cs", "Cn", "Co"}:
            continue
        cleaned.append(char)
    return "".join(cleaned)


def _text_width(draw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def _fit(draw, text: str, font, max_width: float) -> str:
    text = "" if text is None else str(text)
    if _text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if _text_width(draw, text[:mid] + ellipsis, font) <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low] + ellipsis if low else ellipsis


def _fmt_time(value: str, *, with_date: bool) -> str:
    value = str(value or "")
    if len(value) < 16:
        return value or "-"
    if with_date:
        return f"{int(value[5:7])}/{int(value[8:10])} {value[11:16]}"
    return value[11:16]


def _is_replied(row: dict[str, Any]) -> bool:
    if "has_reply" in row:
        return bool(row.get("has_reply"))
    return str(row.get("reply_status") or "") == "replied"


def _count(row: dict[str, Any]) -> int:
    try:
        return max(1, int(float(row.get("gift_count") or 1)))
    except (TypeError, ValueError):
        return 1


def _period_text(date_from: str, date_to: str) -> str:
    if date_from and date_to:
        return f"{date_from} 至 {date_to}"
    if date_from:
        return f"{date_from} 起"
    if date_to:
        return f"截至 {date_to}"
    return "全部时间"


def _draw_badge(draw, right: float, center_y: float, text: str, *, replied: bool, size: int = 17):
    font = _font(size)
    width = _text_width(draw, text, font) + 18
    height = 27
    x0 = right - width
    draw.rounded_rectangle(
        [x0, center_y - height / 2, right, center_y + height / 2],
        radius=8,
        fill=GREEN_BG if replied else PINK_BG,
    )
    draw.text(
        ((x0 + right) / 2, center_y),
        text,
        font=font,
        fill=GREEN if replied else PINK,
        anchor="mm",
    )
    return width


def _draw_header(draw, title: str, period: str, filter_text: str, updated: str) -> int:
    draw.text((WIDTH / 2, 24), title, font=_font(42, bold=True), fill=TITLE, anchor="ma")
    draw.text(
        (WIDTH / 2, 80),
        f"{period} · 数据更新至 {updated or '-'}",
        font=_font(19),
        fill=SUBTITLE,
        anchor="ma",
    )
    y = 104
    if filter_text:
        draw.text((WIDTH / 2, y), f"筛选：{filter_text}", font=_font(17), fill=FAINT, anchor="ma")
        y += 26
    return y + 16


def _section_title(draw, top: int, title: str, hint: str) -> int:
    x = PAD + SECTION_PAD
    draw.rounded_rectangle([x, top + 4, x + 5, top + 34], radius=2, fill=(139, 108, 201))
    draw.text((x + 14, top), title, font=_font(28, bold=True), fill=TITLE, anchor="la")
    if hint:
        draw.text((WIDTH - PAD - SECTION_PAD, top + 10), hint, font=_font(15), fill=FAINT, anchor="ra")
    return top + 54


def _new_canvas(height: int):
    Image, ImageDraw, _ = _pil()
    image = Image.new("RGB", (WIDTH, height), BG)
    return image, ImageDraw.Draw(image)


def _empty_png(message: str) -> bytes:
    height = 260
    image, draw = _new_canvas(height)
    draw.rounded_rectangle(
        [PAD, PAD, WIDTH - PAD, height - PAD], radius=RADIUS, fill=SECTION_BG
    )
    draw.text((WIDTH / 2, height / 2 - 12), message, font=_font(28, bold=True), fill=TITLE, anchor="mm")
    draw.text(
        (WIDTH / 2, height / 2 + 34),
        "请调整筛选条件后重试",
        font=_font(19),
        fill=SUBTITLE,
        anchor="mm",
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _footer(draw, height: int) -> None:
    draw.text(
        (WIDTH / 2, height - 22),
        "陈嘉仪应援会 · 仪嘉人一起加油吧",
        font=_font(13),
        fill=(179, 164, 204),
        anchor="ma",
    )


def render_timeline_png(
    rows: Iterable[dict[str, Any]],
    *,
    period: str,
    filter_text: str = "",
    updated: str = "",
) -> bytes:
    """逐条时间线（最新在前，按天分组）。"""
    items = sorted(
        list(rows),
        key=lambda row: (str(row.get("gift_bj_time") or ""), str(row.get("gift_message_id") or "")),
        reverse=True,
    )
    if not items:
        return _empty_png("当前筛选条件下没有礼物记录")

    day_blocks: list[tuple[str, list[dict[str, Any]]]] = []
    current_day = None
    buffer: list[dict[str, Any]] = []
    for row in items:
        day = str(row.get("gift_bj_time") or "")[:10]
        if day != current_day:
            if buffer:
                day_blocks.append((current_day, buffer))
            current_day, buffer = day, []
        buffer.append(row)
    if buffer:
        day_blocks.append((current_day, buffer))

    section_top = _header_height(filter_text)
    content_top = section_top + 74
    content_height = sum(40 + len(block) * 32 + 10 for _, block in day_blocks)
    section_bottom = content_top + content_height + 10
    height = section_bottom + 42
    image, draw = _new_canvas(height)
    _draw_header(
        draw,
        "房间礼物 · 时间线",
        period,
        filter_text,
        updated,
    )
    draw.rounded_rectangle(
        [PAD, section_top, WIDTH - PAD, section_bottom], radius=RADIUS, fill=SECTION_BG
    )
    _section_title(draw, section_top + 16, "送礼时间线", "红＝待回，绿＝已回；最新在前")

    x0 = PAD + SECTION_PAD
    right = WIDTH - PAD - SECTION_PAD
    time_font = _font(17)
    sender_font = _font(22, bold=True)
    gift_font = _font(21)
    count_font = _font(18, bold=True)
    badge_font = _font(17)
    week = "一二三四五六日"

    y = content_top
    for day, block in day_blocks:
        try:
            weekday = week[dt.datetime.strptime(day, "%Y-%m-%d").weekday()]
        except ValueError:
            weekday = ""
        draw.text(
            (x0, y + 6),
            f"{int(day[5:7])}月{int(day[8:10])}日 周{weekday}",
            font=_font(25, bold=True),
            fill=TITLE,
            anchor="la",
        )
        draw.text((right, y + 14), f"{len(block)} 次", font=_font(16), fill=FAINT, anchor="ra")
        draw.line([x0, y + 37, right, y + 37], fill=LINE, width=2)
        y += 42

        for row in block:
            center_y = y + 16
            replied = _is_replied(row)
            time_text = _fmt_time(str(row.get("gift_bj_time") or ""), with_date=False)
            draw.text((x0, center_y), time_text, font=time_font, fill=FAINT, anchor="lm")
            sender_x = x0 + 78
            sender_text = _fit(draw, _display_text(row.get("sender_name") or "未知用户"), sender_font, 286)
            draw.text((sender_x, center_y), sender_text, font=sender_font, fill=NAME if not replied else MUTED, anchor="lm")
            gift_x = sender_x + 296
            count = _count(row)
            count_text = f"×{count}" if count > 1 else ""
            count_width = _text_width(draw, count_text, count_font) + 10 if count_text else 0
            badge_width = 64
            gift_max = right - badge_width - 10 - count_width - 8 - gift_x
            gift_text = _fit(draw, _display_text(row.get("gift_name") or "-"), gift_font, max(80, gift_max))
            draw.text((gift_x, center_y), gift_text, font=gift_font, fill=NAME if not replied else MUTED, anchor="lm")
            if count_text:
                draw.text(
                    (gift_x + _text_width(draw, gift_text, gift_font) + 8, center_y),
                    count_text,
                    font=count_font,
                    fill=COUNT if not replied else COUNT_DONE,
                    anchor="lm",
                )
            _draw_badge(draw, right, center_y, "已回" if replied else "待回", replied=replied)
            y += 32

        draw.line([x0, y + 4, right, y + 4], fill=(240, 232, 245), width=1)
        y += 10

    _footer(draw, height)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _header_height(filter_text: str) -> int:
    return 124 if filter_text else 110


def _card_height(items: list[dict[str, Any]]) -> int:
    return 42 + len(items) * 29 + 10


def render_overview_png(
    groups: Iterable[dict[str, Any]],
    *,
    period: str,
    filter_text: str = "",
    updated: str = "",
) -> bytes:
    """按送礼人聚合的回复情况卡片（两列）。"""
    group_list = list(groups)
    if not group_list:
        return _empty_png("当前筛选条件下没有送礼记录")

    inner_width = WIDTH - 2 * PAD - 2 * SECTION_PAD
    card_width = (inner_width - CARD_GAP) // 2
    heights = [_card_height(group.get("items") or []) for group in group_list]
    total_height = sum(heights)
    target = total_height / 2

    columns: list[list[int]] = [[], []]
    used = 0.0
    for index, card_h in enumerate(heights):
        column = 0 if used < target or not columns[0] else 1
        columns[column].append(index)
        if column == 0:
            used += card_h
    if not columns[1]:
        columns[1] = columns[0][len(columns[0]) // 2:]
        columns[0] = columns[0][: len(columns[0]) // 2]

    column_heights = [
        sum(heights[index] for index in column) + max(0, len(column) - 1) * 12
        for column in columns
    ]
    section_top = _header_height(filter_text)
    content_top = section_top + 74
    section_bottom = content_top + max(column_heights) + 10
    height = section_bottom + 42
    image, draw = _new_canvas(height)
    _draw_header(
        draw,
        "房间礼物 · 回复情况",
        period,
        filter_text,
        updated,
    )
    draw.rounded_rectangle(
        [PAD, section_top, WIDTH - PAD, section_bottom], radius=RADIUS, fill=SECTION_BG
    )
    _section_title(draw, section_top + 16, "按送礼人汇总", "红＝待回，绿＝已回；按最新送礼时间排")

    x0 = PAD + SECTION_PAD
    for column_index, column in enumerate(columns):
        x = x0 + column_index * (card_width + CARD_GAP)
        y = content_top
        for index in column:
            group = group_list[index]
            items = group.get("items") or []
            card_h = heights[index]
            draw.rounded_rectangle(
                [x, y, x + card_width, y + card_h],
                radius=10,
                fill=CARD_BG,
                outline=CARD_BORDER,
                width=1,
            )
            name_font = _font(23, bold=True)
            name = _fit(draw, _display_text(group.get("sender_name") or "未知用户"), name_font, card_width - 24)
            draw.text((x + 12, y + 10), name, font=name_font, fill=NAME, anchor="la")
            row_y = y + 42
            time_font = _font(16)
            gift_font = _font(20)
            count_font = _font(17, bold=True)
            for row in items:
                center_y = row_y + 14
                replied = _is_replied(row)
                time_text = _fmt_time(str(row.get("gift_bj_time") or ""), with_date=True)
                draw.text((x + 12, center_y), time_text, font=time_font, fill=FAINT, anchor="lm")
                gift_x = x + 12 + 106
                right = x + card_width - 12
                count = _count(row)
                count_text = f"×{count}" if count > 1 else ""
                count_width = _text_width(draw, count_text, count_font) + 8 if count_text else 0
                badge_width = 58
                gift_max = right - badge_width - 8 - count_width - 8 - gift_x
                gift_text = _fit(draw, _display_text(row.get("gift_name") or "-"), gift_font, max(50, gift_max))
                draw.text((gift_x, center_y), gift_text, font=gift_font, fill=NAME if not replied else MUTED, anchor="lm")
                if count_text:
                    draw.text(
                        (gift_x + _text_width(draw, gift_text, gift_font) + 6, center_y),
                        count_text,
                        font=count_font,
                        fill=COUNT if not replied else COUNT_DONE,
                        anchor="lm",
                    )
                _draw_badge(draw, right, center_y, "已回" if replied else "待回", replied=replied, size=16)
                row_y += 29
            y += card_h + 12

    _footer(draw, height)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()

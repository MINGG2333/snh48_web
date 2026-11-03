"""红蓝计分汇总 PNG 导出（Pillow 服务端渲染）。

版式对齐 `private_handover/移交包/嘉仪业务/礼物回复/礼物回复时间线_近三周_20261021.png`：
浅紫底、白色卡片、紫色标题、单栏时间线；按昵称汇总按最长昵称动态定宽，按条目按最长昵称/业务名动态定宽（最小 820px），正文 20–27px。
未登记口袋48昵称的条目不再标红，昵称统一颜色，只在名字后保留一个低对比度 ! 标记。
按条目导出最后一列显示选定业务名，仅业务名，多个业务用 + 连接。
"""
from __future__ import annotations

import datetime as dt
import io
import re
from collections import OrderedDict
from typing import Any, Iterable

from website.gift_reply_export import (
    BG,
    CARD_BG,
    CARD_BORDER,
    FAINT,
    LINE,
    MUTED,
    NAME,
    SECTION_BG,
    SUBTITLE,
    TITLE,
    _display_text,
    _font as _gift_font,
    _pil,
    _text_width,
)

WIDTH = 1000
ENTRIES_WIDTH = 820
PAD = 24
FAN_COLS = 2
FAN_GAP = 14
FAN_CARD_HEIGHT = 76
FAN_NAME_SIZE = 22
FAN_SCORE_SIZE = 28
FAN_BADGE_SIZE = 18
CARD_RADIUS = 14
SCORING_LABELS = {"计分卡": "计分卡", "鸡腿": "鸡腿"}
SCORING_COLORS = {
    "计分卡": ((55, 115, 190), (228, 238, 255)),
    "鸡腿": ((173, 58, 107), (251, 227, 238)),
}


def _font(size: int, bold: bool = False):
    return _gift_font(size, bold, scale=1)


def _score(value: Any) -> str:
    number = float(value or 0)
    if abs(number - round(number)) < 0.0001:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _draw_header(draw, title: str, period: str, filter_text: str, updated: str, width: int = WIDTH) -> int:
    draw.text((width / 2, 22), title, font=_font(50, bold=True), fill=TITLE, anchor="ma")
    draw.text(
        (width / 2, 84),
        f"{period} · 数据更新至 {updated or '-'}",
        font=_font(22),
        fill=SUBTITLE,
        anchor="ma",
    )
    y = 118
    if filter_text:
        draw.text((width / 2, y), f"筛选：{filter_text}", font=_font(18), fill=FAINT, anchor="ma")
        y += 28
    return y + 10


def _section_title(draw, top: int, title: str, hint: str = "") -> int:
    x = PAD + 20
    draw.rounded_rectangle([x, top + 4, x + 5, top + 38], radius=2, fill=(139, 108, 201))
    draw.text((x + 14, top), title, font=_font(32, bold=True), fill=TITLE, anchor="la")
    if hint:
        draw.text((WIDTH - PAD - 20, top + 12), hint, font=_font(20), fill=FAINT, anchor="ra")
    return top + 70


def _badge(draw, x: float, y: float, text: str, color, bg, *, size: int = 18) -> float:
    font = _font(size)
    width = _text_width(draw, text, font) + 16
    height = size + 10
    draw.rounded_rectangle([x, y, x + width, y + height], radius=8, fill=bg)
    draw.text((x + width / 2, y + height / 2 - 1), text, font=font, fill=color, anchor="mm")
    return width


def _warn_icon(draw, x: float, center_y: float) -> None:
    """未登记昵称标记：低对比度圆圈 + 同色系叹号，不再使用红色。"""
    radius = 9
    draw.ellipse(
        [x, center_y - radius, x + 2 * radius, center_y + radius],
        fill=(235, 230, 242),
    )
    draw.text(
        (x + radius, center_y - 1),
        "!",
        font=_font(12, bold=True),
        fill=MUTED,
        anchor="mm",
    )


def _summary_card_width(draw, fans: list[dict[str, Any]]) -> float:
    name_font = _font(FAN_NAME_SIZE, bold=True)
    score_font = _font(FAN_SCORE_SIZE, bold=True)
    badge_font = _font(FAN_BADGE_SIZE)
    width = 0.0
    for fan in fans:
        name = _display_text(fan.get("fan_name") or "未登记")
        name_width = _text_width(draw, name, name_font) + (26 if fan.get("warning") else 0)
        score_width = _text_width(draw, _score(fan.get("total_score")), score_font)
        width = max(width, 16 + name_width + 10 + score_width + 16)
        scoring = fan.get("scoring") or {}
        badge_width = 0.0
        for method in ("计分卡", "鸡腿"):
            if method not in scoring:
                continue
            label = f"{SCORING_LABELS.get(method, method)} {_score(scoring[method])}"
            badge_width += _text_width(draw, label, badge_font) + 16 + 6
        if badge_width:
            width = max(width, 16 + badge_width + 16)
    return width


def _fan_card(draw, x: float, y: int, width: float, fan: dict[str, Any]) -> int:
    height = FAN_CARD_HEIGHT
    draw.rounded_rectangle([x, y, x + width, y + height], radius=12, fill=CARD_BG, outline=CARD_BORDER)
    warning = bool(fan.get("warning"))
    name_font = _font(FAN_NAME_SIZE, bold=True)
    name = _display_text(fan.get("fan_name") or "未登记")
    draw.text((x + 16, y + 10), name, font=name_font, fill=NAME, anchor="la")
    if warning:
        _warn_icon(draw, x + 16 + _text_width(draw, name, name_font) + 6, y + 21)
    draw.text(
        (x + width - 16, y + 6),
        _score(fan.get("total_score")),
        font=_font(FAN_SCORE_SIZE, bold=True),
        fill=TITLE,
        anchor="ra",
    )
    scoring = fan.get("scoring") or {}
    badge_x = x + 16
    badge_y = y + 45
    for method in ("计分卡", "鸡腿"):
        if method not in scoring:
            continue
        label = f"{SCORING_LABELS.get(method, method)} {_score(scoring[method])}"
        color, bg = SCORING_COLORS.get(method, (MUTED, (240, 240, 240)))
        badge_x += _badge(draw, badge_x, badge_y, label, color, bg, size=FAN_BADGE_SIZE) + 6
    return height


def _draw_fans(draw, top: int, fans: list[dict[str, Any]], *, width: int, card_w: float) -> int:
    grid_w = FAN_COLS * card_w + (FAN_COLS - 1) * FAN_GAP
    left = (width - grid_w) / 2
    ys = [top] * FAN_COLS
    for index, fan in enumerate(fans):
        col = index % FAN_COLS
        height = _fan_card(draw, left + col * (card_w + FAN_GAP), ys[col], card_w, fan)
        ys[col] += height + 12
    return max(ys) + 10


def _business_text(row: dict[str, Any]) -> str:
    """Selected business names only, joined with '+' (score prefixes removed)."""
    names: list[str] = []
    for key in ("selected_business", "selected_business_bonus"):
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        name = re.sub(r"^\d+-", "", value).strip()
        if name and name not in names:
            names.append(name)
    return "+".join(names)


def _draw_entries(
    draw,
    top: int,
    entries: list[dict[str, Any]],
    width: int = WIDTH,
    source_offset: int = 300,
) -> int:
    groups: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for entry in entries:
        day = str(entry.get("source_time") or entry.get("created_at") or "")[:10] or "未标日期"
        groups.setdefault(day, []).append(entry)
    if not groups:
        return top

    section_top = top
    row_h = 44
    day_h = 46
    content_height = sum(day_h + len(rows) * row_h + 12 for rows in groups.values())
    section_bottom = section_top + 74 + content_height + 14
    draw.rounded_rectangle(
        [PAD, section_top, width - PAD, section_bottom], radius=CARD_RADIUS, fill=SECTION_BG
    )
    x0 = PAD + 20
    right = width - PAD - 20
    draw.rounded_rectangle([x0, section_top + 16, x0 + 5, section_top + 48], radius=2, fill=(139, 108, 201))
    draw.text((x0 + 14, section_top + 10), "计分时间线", font=_font(32, bold=True), fill=TITLE, anchor="la")
    draw.text((right, section_top + 22), "按时间正序", font=_font(20), fill=FAINT, anchor="ra")

    week = "一二三四五六日"
    y = section_top + 74
    time_font = _font(20)
    name_font = _font(24, bold=True)
    score_font = _font(22)
    business_font = _font(18)
    for day, rows in groups.items():
        try:
            weekday = week[dt.datetime.strptime(day, "%Y-%m-%d").weekday()]
        except ValueError:
            weekday = ""
        draw.text(
            (x0, y),
            f"{int(day[5:7])}月{int(day[8:10])}日 周{weekday}",
            font=_font(27, bold=True),
            fill=TITLE,
            anchor="la",
        )
        draw.text((right, y + 7), f"{len(rows)} 条", font=_font(18), fill=FAINT, anchor="ra")
        draw.line([x0, y + 36, right, y + 36], fill=LINE, width=1)
        y += day_h
        for row in rows:
            center_y = y + row_h / 2
            time_text = str(row.get("source_time") or row.get("created_at") or "")[11:16] or "-"
            draw.text((x0, center_y), time_text, font=time_font, fill=FAINT, anchor="lm")

            name = row.get("fan_name") or row.get("raw_name") or "未登记"
            name_x = x0 + 70
            source_x = x0 + source_offset
            score_x = source_x + 100
            warning = bool(row.get("warning"))
            name_text = _display_text(name)
            draw.text((name_x, center_y), name_text, font=name_font, fill=NAME, anchor="lm")
            if warning:
                _warn_icon(draw, name_x + _text_width(draw, name_text, name_font) + 8, center_y)

            method = row.get("scoring_method") or "计分卡"
            color, bg = SCORING_COLORS.get(method, (MUTED, (240, 240, 240)))
            _badge(draw, source_x, center_y - 14, SCORING_LABELS.get(method, method), color, bg, size=18)
            score_text = f"送出了 {_score(row.get('score'))} 分"
            draw.text(
                (score_x, center_y),
                score_text,
                font=score_font,
                fill=MUTED if row.get("duplicate") else NAME,
                anchor="lm",
            )
            business = _business_text(row)
            if business:
                draw.text((right, center_y), _display_text(business), font=business_font, fill=SUBTITLE, anchor="rm")

            y += row_h
        draw.line([x0, y + 6, right, y + 6], fill=(240, 232, 245), width=1)
        y += 14
    return section_bottom + 12


def _footer(draw, height: int, width: int = WIDTH) -> None:
    note_y = height - 60
    _warn_icon(draw, PAD, note_y + 9)
    draw.text(
        (PAD + 24, note_y),
        "表示暂未找到对应的口袋48账号昵称",
        font=_font(18),
        fill=(120, 100, 150),
        anchor="la",
    )
    draw.text(
        (width / 2, height - 24),
        "陈嘉仪应援会 · 红蓝计分汇总",
        font=_font(16),
        fill=(179, 164, 204),
        anchor="ma",
    )


def _render(title: str, body, *, period: str, filter_text: str, updated: str, estimated_height: int = 2000, width: int = WIDTH) -> bytes:
    Image, ImageDraw, _ = _pil()
    image = Image.new("RGB", (width, max(600, estimated_height + 140)), BG)
    draw = ImageDraw.Draw(image)
    top = _draw_header(draw, title, period, filter_text, updated, width=width)
    top = body(draw, top, width)
    content_height = max(400, top + 80)
    image = image.crop((0, 0, width, content_height))
    draw = ImageDraw.Draw(image)
    _footer(draw, content_height, width=width)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_summary_png(
    entries: Iterable[dict[str, Any]],
    *,
    summary: dict[str, Any],
    fan_summary: Iterable[dict[str, Any]],
    period: str,
    filter_text: str = "",
    updated: str = "",
) -> bytes:
    fans = list(fan_summary)
    Image, ImageDraw, _ = _pil()
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    card_w = _summary_card_width(measure, fans) if fans else 0
    grid_w = FAN_COLS * card_w + (FAN_COLS - 1) * FAN_GAP
    title = "红蓝计分汇总 · 按昵称汇总"
    header_w = max(
        _text_width(measure, title, _font(50, bold=True)),
        _text_width(measure, f"{period} · 数据更新至 {updated or '-'}", _font(22)),
        _text_width(measure, f"筛选：{filter_text}", _font(18)) if filter_text else 0,
    ) + 2 * PAD
    width = int(max(grid_w + 2 * PAD, header_w))

    def body(draw, top, width):
        return _draw_fans(draw, top, fans, width=width, card_w=card_w)

    estimated = 300 + ((len(fans) + FAN_COLS - 1) // FAN_COLS) * (FAN_CARD_HEIGHT + 12) + 80
    return _render(
        title,
        body,
        period=period,
        filter_text=filter_text,
        updated=updated,
        estimated_height=estimated,
        width=width,
    )


def render_entries_png(
    entries: Iterable[dict[str, Any]],
    *,
    summary: dict[str, Any],
    period: str,
    filter_text: str = "",
    updated: str = "",
) -> bytes:
    items = list(entries)
    title = "红蓝计分汇总 · 按条目"
    Image, ImageDraw, _ = _pil()
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    name_font = _font(24, bold=True)
    score_font = _font(22)
    business_font = _font(18)
    max_name_width = 0
    for item in items:
        name = item.get("fan_name") or item.get("raw_name") or "未登记"
        name_width = _text_width(measure, _display_text(name), name_font) + (26 if item.get("warning") else 0)
        max_name_width = max(max_name_width, name_width)
    source_offset = max(300, 70 + int(max_name_width) + 16)
    width = ENTRIES_WIDTH
    for item in items:
        business = _business_text(item)
        business_width = _text_width(measure, _display_text(business), business_font) if business else 0
        score_text = f"送出了 {_score(item.get('score'))} 分"
        required = (
            204
            + source_offset
            + _text_width(measure, score_text, score_font)
            + business_width
        )
        width = max(width, int(required) + 1)
    header_w = max(
        _text_width(measure, title, _font(50, bold=True)),
        _text_width(measure, f"{period} · 数据更新至 {updated or '-'}", _font(22)),
        _text_width(measure, f"筛选：{filter_text}", _font(18)) if filter_text else 0,
    ) + 2 * PAD
    width = max(width, int(header_w))

    def body(draw, top, width):
        return _draw_entries(draw, top, items, width=width, source_offset=source_offset)

    day_rows: "OrderedDict[str, int]" = OrderedDict()
    for item in items:
        day = str(item.get("source_time") or item.get("created_at") or "")[:10] or "未标日期"
        day_rows[day] = day_rows.get(day, 0) + 1
    estimated = 280 + sum(46 + count * 44 + 12 for count in day_rows.values()) + 80
    return _render(
        title,
        body,
        period=period,
        filter_text=filter_text,
        updated=updated,
        estimated_height=estimated,
        width=width,
    )

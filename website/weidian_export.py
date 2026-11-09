"""微店订单筛选结果 PNG 导出。

版式与红蓝台账「按条目导出」保持一致：浅紫底、白色卡片、紫色标题。
本页只导出三列：商品名 / 播报名 / 金额，并在底部给出筛选结果的单数与合计。
"""
from __future__ import annotations

import io
from typing import Any, Iterable

from website.gift_reply_export import (
    BG,
    FAINT,
    LINE,
    NAME,
    SECTION_BG,
    SUBTITLE,
    TITLE,
    _display_text,
    _draw_text_fallback,
    _fallback_for,
    _font as _gift_font,
    _pil,
    _text_width,
    _text_width_fallback,
)

PAD = 24
MIN_WIDTH = 900
ROW_HEIGHT = 46
HEADER_HEIGHT = 48
MAX_ITEM_WIDTH = 520
MAX_NAME_WIDTH = 260
AMOUNT_WIDTH = 150
COLUMN_GAP = 28


def _font(size: int, bold: bool = False):
    return _gift_font(size, bold, scale=1)


def mask_name(value: Any) -> str:
    """与页面保持一致的匿名打码：保留首字，其余替换为 **。"""
    text = str(value or "").strip()
    if not text:
        return "匿名"
    chars = list(text)
    if len(chars) <= 1:
        return "*"
    return chars[0] + "**"


def _amount(value: Any) -> str:
    return f"¥{float(value or 0):.2f}"


def _fit_text(draw, text: Any, font, fallback, max_width: float) -> str:
    rendered = _display_text(text, font, fallback)
    if _text_width_fallback(draw, rendered, font, fallback) <= max_width:
        return rendered
    ellipsis = "…"
    shortened = rendered
    while shortened and _text_width_fallback(draw, shortened + ellipsis, font, fallback) > max_width:
        shortened = shortened[:-1]
    return (shortened + ellipsis) if shortened else ellipsis


def render_orders_png(
    rows: Iterable[dict[str, Any]],
    *,
    filter_text: str = "",
    updated: str = "",
    title: str = "微店订单导出",
    mask_names: bool = False,
) -> bytes:
    items = list(rows)
    Image, ImageDraw, _ = _pil()
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    item_font = _font(22)
    item_fallback = _fallback_for(item_font)
    name_font = _font(22, bold=True)
    name_fallback = _fallback_for(name_font)
    amount_font = _font(22)
    header_font = _font(20, bold=True)
    total_font = _font(24, bold=True)

    item_width = 0.0
    name_width = 0.0
    amount_width = max(
        _text_width(measure, _amount(0), amount_font),
        _text_width(measure, _amount(100000), amount_font),
    )
    for row in items:
        item_text = _display_text(row.get("item_name") or "未知商品", item_font, item_fallback)
        item_width = max(
            item_width,
            _text_width_fallback(measure, item_text, item_font, item_fallback),
        )
        display = row.get("display_name") or row.get("receiver_name") or "匿名"
        name_text = mask_name(display) if mask_names else str(display)
        name_width = max(
            name_width,
            _text_width_fallback(measure, _display_text(name_text, name_font, name_fallback), name_font, name_fallback),
        )
        amount_width = max(amount_width, _text_width(measure, _amount(row.get("amount")), amount_font))

    item_width = min(item_width, MAX_ITEM_WIDTH)
    name_width = min(name_width, MAX_NAME_WIDTH)
    columns_width = PAD * 2 + 24 * 2 + item_width + COLUMN_GAP + name_width + COLUMN_GAP + amount_width
    total = round(sum(float(row.get("amount") or 0) for row in items), 2)
    subtitle_text = f"{len(items)} 单 · 合计 {_amount(total)}"
    if filter_text:
        subtitle_text += f" · 筛选：{filter_text}"
    updated_text = f"数据更新至 {updated or '-'}"
    title_font = _font(42, bold=True)
    subtitle_font = _font(20)
    subtitle_fallback = _fallback_for(subtitle_font)
    header_width = max(
        _text_width(measure, title, title_font),
        _text_width_fallback(measure, _display_text(subtitle_text, subtitle_font, subtitle_fallback), subtitle_font, subtitle_fallback),
        _text_width(measure, updated_text, _font(18)),
    ) + 2 * PAD
    width = int(max(MIN_WIDTH, columns_width, min(header_width, 1400)))
    item_x = PAD + 24
    name_x = item_x + item_width + COLUMN_GAP
    amount_right = width - PAD - 24

    card_top = 164
    card_height = 18 + HEADER_HEIGHT + len(items) * ROW_HEIGHT + 62 + 18
    card_bottom = card_top + card_height
    estimated_height = card_bottom + 80 + (28 if mask_names else 0)
    image = Image.new("RGB", (width, estimated_height), BG)
    draw = ImageDraw.Draw(image)

    draw.text((width / 2, 12), title, font=title_font, fill=TITLE, anchor="mt")
    subtitle_text = _fit_text(draw, subtitle_text, subtitle_font, subtitle_fallback, width - 2 * PAD)
    draw.text((width / 2, 92), subtitle_text, font=subtitle_font, fill=SUBTITLE, anchor="mt")
    draw.text((width / 2, 122), updated_text, font=_font(18), fill=FAINT, anchor="mt")

    draw.rounded_rectangle(
        [PAD, card_top, width - PAD, card_bottom],
        radius=14,
        fill=SECTION_BG,
        outline=(236, 227, 245),
    )

    y = card_top + 18
    draw.text((item_x, y), "商品名", font=header_font, fill=FAINT, anchor="la")
    draw.text((name_x, y), "播报名", font=header_font, fill=FAINT, anchor="la")
    draw.text((amount_right, y), "金额", font=header_font, fill=FAINT, anchor="ra")
    y += HEADER_HEIGHT - 14
    draw.line([item_x, y, amount_right, y], fill=LINE, width=1)
    y += 14

    for row in items:
        center_y = y + ROW_HEIGHT / 2
        item_text = _fit_text(draw, row.get("item_name") or "未知商品", item_font, item_fallback, item_width)
        display = row.get("display_name") or row.get("receiver_name") or "匿名"
        name_text = mask_name(display) if mask_names else str(display)
        name_text = _fit_text(draw, name_text, name_font, name_fallback, name_width)
        _draw_text_fallback(draw, (item_x, center_y), item_text, item_font, item_fallback, fill=NAME, anchor="lm")
        _draw_text_fallback(draw, (name_x, center_y), name_text, name_font, name_fallback, fill=NAME, anchor="lm")
        draw.text((amount_right, center_y), _amount(row.get("amount")), font=amount_font, fill=NAME, anchor="rm")
        y += ROW_HEIGHT
        draw.line([item_x, y - 6, amount_right, y - 6], fill=(240, 232, 245), width=1)

    y += 6
    draw.line([item_x, y, amount_right, y], fill=LINE, width=2)
    y += 16
    draw.text((item_x, y), "合计", font=total_font, fill=TITLE, anchor="la")
    draw.text((name_x, y + 2), f"{len(items)} 单", font=_font(20), fill=SUBTITLE, anchor="la")
    draw.text((amount_right, y), _amount(total), font=total_font, fill=TITLE, anchor="ra")

    if mask_names:
        draw.text((item_x, card_bottom + 12), "播报名已匿名打码（首字 + **）", font=_font(16), fill=FAINT, anchor="la")

    footer_y = estimated_height - 26
    draw.text(
        (width / 2, footer_y),
        "陈嘉仪应援会 · 微店订单导出",
        font=_font(15),
        fill=(179, 164, 204),
        anchor="ma",
    )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()

"""微店订单筛选结果 PNG 导出。

版式与红蓝台账「按条目导出」相近：浅紫底、白色卡片、紫色标题。
只保留三列：商品名 / 播报名 / 金额；无表头、无合计行。
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
    TITLE,
    _display_text,
    _draw_text_fallback,
    _fallback_for,
    _font as _gift_font,
    _pil,
    _text_width,
    _text_width_fallback,
)

PAD = 20
MIN_WIDTH = 560
ROW_HEIGHT = 44
MAX_ITEM_WIDTH = 360
MAX_NAME_WIDTH = 140
COLUMN_GAP = 22


def _font(size: int, bold: bool = False):
    return _gift_font(size, bold, scale=1)


def mask_name(value: Any) -> str:
    """与页面保持一致的匿名打码：3 字及以上保留首尾，其余替换为 **。"""
    text = str(value or "").strip()
    if not text:
        return "匿名"
    chars = list(text)
    if len(chars) <= 1:
        return "*"
    if len(chars) == 2:
        return chars[0] + "**"
    return chars[0] + "**" + chars[-1]


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


def _row_time(row: dict[str, Any]) -> str:
    return str(row.get("add_time") or row.get("paid_at") or row.get("update_time") or "")


def render_orders_png(
    rows: Iterable[dict[str, Any]],
    *,
    updated: str = "",
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
    title = "应援会账目"
    title_font = _font(42, bold=True)

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
    item_x = PAD + 24
    name_x = item_x + item_width + COLUMN_GAP
    amount_right = name_x + name_width + COLUMN_GAP + amount_width
    updated_text = f"数据更新至 {updated or '-'}"
    updated_width = _text_width(measure, updated_text, _font(18))
    width = int(max(MIN_WIDTH, amount_right + PAD + 4, _text_width(measure, title, title_font) + 2 * PAD, updated_width + 2 * PAD))

    card_top = 100
    card_height = 18 + len(items) * ROW_HEIGHT + 18
    card_bottom = card_top + card_height
    estimated_height = card_bottom + 58 + (24 if mask_names else 0)
    image = Image.new("RGB", (width, estimated_height), BG)
    draw = ImageDraw.Draw(image)

    draw.text((width / 2, 12), title, font=title_font, fill=TITLE, anchor="mt")
    draw.text((width / 2, 66), updated_text, font=_font(18), fill=FAINT, anchor="mt")

    draw.rounded_rectangle(
        [PAD, card_top, width - PAD, card_bottom],
        radius=14,
        fill=SECTION_BG,
        outline=(236, 227, 245),
    )

    y = card_top + 18
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
        if y < card_bottom - 6:
            draw.line([item_x, y - 6, amount_right, y - 6], fill=(240, 232, 245), width=1)

    if mask_names:
        draw.text((item_x, card_bottom + 10), "播报名已匿名打码（3 字及以上保留首尾）", font=_font(16), fill=FAINT, anchor="la")

    draw.text(
        (width / 2, estimated_height - 24),
        "陈嘉仪应援会 · 应援会账目",
        font=_font(15),
        fill=(179, 164, 204),
        anchor="ma",
    )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()

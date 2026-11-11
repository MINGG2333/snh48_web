"""礼物回复页 PNG 导出（Pillow 服务端渲染）。

两个版式与交接包手工图一致：
- 时间线：单栏，按天分组，最新在前，适合逐条查看；
- 回复情况：按送礼人聚合，两列卡片，红=待回、绿=已回。
版式与字号对齐交接包本地图（1000px 逻辑宽，正文 20-24px），
按 2x 像素密度渲染（输出 2000px 宽），长图放大或在高分屏上更清晰。

只依赖 Pillow 与系统 CJK 字体（阿里云文泉驿/腾讯云 Noto 均可）；备用字体链为
仓库内置 Noto Sans Egyptian Hieroglyphs、仓库内置单色 Noto Emoji（emoji 统一为
黑/白线稿，不使用彩色 emoji），再接系统 FreeSerif/Unifont/DejaVu，覆盖埃及圣书体、
kaomoji 特殊字符、符号和 emoji。

昵称按“字素簇”处理：emoji 的 ZWJ 组合、变体选择符、肤色修饰符和 keycap 会作为整体
选字体并交给 HarfBuzz 塑形，避免 👨‍👩‍👧、1️⃣ 这类组合被拆成多个字符。
"""
from __future__ import annotations

import datetime as dt
import io
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

SCALE = 2
WIDTH = 1000
PAD = 24
SECTION_PAD = 20
CARD_GAP = 14
RADIUS = 14
MAX_EXPORT_PIXELS = 105_000_000


class ExportTooLarge(Exception):
    """导出图超过安全像素预算，避免长图渲染拖垮小内存节点。"""


def _check_export_size(height: int) -> None:
    pixels = WIDTH * SCALE * height * SCALE
    if pixels > MAX_EXPORT_PIXELS:
        raise ExportTooLarge("导出图过长，请缩小日期范围或增加筛选条件后重试")

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
FALLBACK_FONT_PATHS = (
    Path(__file__).resolve().parent / "static" / "fonts" / "NotoSansEgyptianHieroglyphs-Regular.ttf",
    Path(__file__).resolve().parent / "static" / "fonts" / "NotoEmoji-Regular.ttf",
    Path("/usr/share/fonts/truetype/freefont/FreeSerif.ttf"),
    Path("/usr/share/fonts/truetype/unifont/unifont.ttf"),
    Path("/usr/share/fonts/truetype/unifont/unifont_upper.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
)
FALLBACK_FONT_PATH = FALLBACK_FONT_PATHS[0]
EMOJI_FONT_PATH = FALLBACK_FONT_PATHS[1]
# 单色 emoji 字形比中日韩字形略小，按同一字号绘制会显得偏小，统一放大一点。
EMOJI_FONT_SCALE = 1.15


def _pil():
    from PIL import Image, ImageDraw, ImageFont

    return Image, ImageDraw, ImageFont


class _ScaledDraw:
    """在 2x 画布上按 1000px 逻辑坐标绘制，输出图更清晰。"""

    def __init__(self, draw, scale: int):
        self._draw = draw
        self._scale = scale

    def _xy(self, xy):
        scale = self._scale
        if hasattr(xy[0], "__len__"):
            return [(x * scale, y * scale) for x, y in xy]
        return [value * scale for value in xy]

    def text(self, xy, text, *args, **kwargs):
        return self._draw.text(self._xy(xy), text, *args, **kwargs)

    def line(self, xy, *args, **kwargs):
        kwargs["width"] = max(1, round(kwargs.get("width", 1) * self._scale))
        return self._draw.line(self._xy(xy), *args, **kwargs)

    def rounded_rectangle(self, xy, *args, **kwargs):
        kwargs["radius"] = round(kwargs.get("radius", 0) * self._scale)
        kwargs["width"] = max(1, round(kwargs.get("width", 1) * self._scale))
        return self._draw.rounded_rectangle(self._xy(xy), *args, **kwargs)

    def textlength(self, text, font=None):
        return self._draw.textlength(text, font=font) / self._scale


@lru_cache(maxsize=256)
def _font(size: int, bold: bool = False, scale: int = SCALE):
    _, _, ImageFont = _pil()
    candidates = BOLD_CANDIDATES if bold else FONT_CANDIDATES
    scaled = max(1, round(size * scale))
    for path in candidates:
        try:
            return ImageFont.truetype(path, scaled)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=scaled)
    except TypeError:
        return ImageFont.load_default()


@lru_cache(maxsize=8)
def _missing_glyph_mask(font) -> bytes:
    """字体缺失字形通常共用同一个 .notdef 位图，用未分配码位取样。"""
    try:
        return bytes(font.getmask("\U0010FFFF", mode="L"))
    except (AttributeError, OSError, ValueError):
        return b""


@lru_cache(maxsize=65536)
def _glyph_is_missing(font, char: str) -> bool:
    if char.isspace():
        return False
    mask = _missing_glyph_mask(font)
    try:
        glyph = bytes(font.getmask(char, mode="L"))
    except (AttributeError, OSError, ValueError):
        return True
    if mask:
        return glyph == mask
    # 没有 .notdef 位图的字体无法按位图比对，退化为“有没有墨迹”判断。
    if glyph:
        return False
    try:
        return font.getbbox(char) is None
    except (AttributeError, OSError, ValueError):
        return True


_ZWJ = "\u200d"
_VARIATION_SELECTORS = frozenset({"\ufe0e", "\ufe0f"})
_SKIP_CATEGORIES = frozenset({"Cs", "Cn", "Co"})


def _is_emoji_modifier(char: str) -> bool:
    return "\U0001F3FB" <= char <= "\U0001F3FF"


def _is_joinable(char: str) -> bool:
    if char == _ZWJ or char in _VARIATION_SELECTORS or _is_emoji_modifier(char):
        return True
    return unicodedata.category(char) in {"Mn", "Me", "Mc"}


def _clusters(text: str) -> list[str]:
    """按字素簇切分：基字符带组合标记/变体选择符/肤色修饰，或以 ZWJ 连成 emoji 序列。"""
    clusters: list[str] = []
    for char in text:
        if clusters and (_is_joinable(char) or clusters[-1].endswith(_ZWJ)):
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters


def _is_invisible(char: str) -> bool:
    return char == _ZWJ or char in _VARIATION_SELECTORS


def _font_covers(font, text: str) -> bool:
    """整段文字（含 emoji 组合）能否都由同一字体渲染。"""
    if font is None:
        return False
    for char in text:
        if _is_invisible(char) or char.isspace():
            continue
        if _glyph_is_missing(font, char):
            return False
    return True


@lru_cache(maxsize=64)
def _fallback_fonts(size: int):
    """补充 WQY/Noto CJK 不含的装饰字符、符号和 emoji（单色）。"""
    _, _, ImageFont = _pil()
    fonts = []
    for path in FALLBACK_FONT_PATHS:
        scaled = round(size * EMOJI_FONT_SCALE) if path == EMOJI_FONT_PATH else round(size)
        try:
            fonts.append(ImageFont.truetype(str(path), max(1, scaled)))
        except OSError:
            continue
    return tuple(fonts)


def _fallback_for(font):
    size = getattr(font, "size", None)
    if not size:
        return ()
    return _fallback_fonts(int(size))


def _fallback_list(fallback):
    if fallback is None:
        return ()
    if isinstance(fallback, (list, tuple)):
        return tuple(fallback)
    return (fallback,)


def _pick_font(char: str, font, fallbacks):
    if not _glyph_is_missing(font, char):
        return font
    for fallback in fallbacks:
        if not _glyph_is_missing(fallback, char):
            return fallback
    return font


def _pick_cluster_font(cluster: str, font, fallbacks):
    """为整个字素簇挑一个能渲染全部可见字符的字体，保证 emoji 组合不被拆开。"""
    for candidate in (font, *fallbacks):
        if _font_covers(candidate, cluster):
            return candidate
    return None


def _font_runs(text: str, font, fallback=None):
    fallbacks = _fallback_list(fallback)
    runs: list[list[Any]] = []
    for cluster in _clusters(text):
        use = _pick_cluster_font(cluster, font, fallbacks)
        if use is not None:
            pieces = [(cluster, use)]
        else:
            # 同一簇里没有单一字体能全渲染时，退回逐字挑字体并丢掉真的缺字部分。
            pieces = []
            for char in cluster:
                if _is_invisible(char):
                    if pieces:
                        pieces[-1] = (pieces[-1][0] + char, pieces[-1][1])
                    continue
                chosen = _pick_cluster_font(char, font, fallbacks)
                if chosen is None:
                    continue
                pieces.append((char, chosen))
        for piece, use in pieces:
            if runs and runs[-1][1] is use:
                runs[-1][0] += piece
            else:
                runs.append([piece, use])
    return runs


def _text_width_fallback(draw, text: str, font, fallback=None) -> float:
    fallbacks = _fallback_list(fallback if fallback is not None else _fallback_for(font))
    if not fallbacks:
        return draw.textlength(text, font=font)
    return sum(draw.textlength(run, font=use) for run, use in _font_runs(text, font, fallbacks))


def _draw_text_fallback(draw, xy, text: str, font, fallback=None, **kwargs):
    fallbacks = _fallback_list(fallback if fallback is not None else _fallback_for(font))
    if not fallbacks:
        return draw.text(xy, text, font=font, **kwargs)
    runs = _font_runs(text, font, fallbacks)
    if len(runs) <= 1 and (not runs or runs[0][1] is font):
        return draw.text(xy, text, font=font, **kwargs)
    anchor = kwargs.pop("anchor", None) or "la"
    total = sum(draw.textlength(run, font=use) for run, use in runs)
    x, y = xy
    horizontal = anchor[0] if anchor else "l"
    vertical = anchor[1] if len(anchor) > 1 else "a"
    if horizontal == "r":
        cursor = x - total
    elif horizontal == "m":
        cursor = x - total / 2
    else:
        cursor = x
    scale = getattr(draw, "_scale", 1) or 1
    ascent, descent = font.getmetrics()
    ascent /= scale
    descent /= scale
    if vertical == "m":
        baseline = y + (ascent - descent) / 2
    elif vertical == "s":
        baseline = y
    elif vertical == "d":
        baseline = y - descent
    else:
        baseline = y + ascent
    for run, use in runs:
        draw.text((cursor, baseline), run, font=use, anchor="ls", **kwargs)
        cursor += draw.textlength(run, font=use)


def _display_text(text: Any, font=None, fallback_font=None) -> str:
    """去掉主字体和备用字体链都无法渲染的字符，避免导出图出现方框。

    保留能渲染的 kaomoji 装饰字符（如 ᴗ、ʕ、ˊ）、符号和 emoji；emoji 的 ZWJ 组合、
    变体选择符、肤色修饰符和 keycap 作为字素簇整体保留，交给字体塑形。
    """
    value = "" if text is None else str(text)
    fallbacks = _fallback_list(fallback_font)
    candidates = tuple(item for item in (font, *fallbacks) if item is not None)
    if not candidates:
        return "".join(ch for ch in value if unicodedata.category(ch) not in _SKIP_CATEGORIES)
    kept: list[str] = []
    for cluster in _clusters(value):
        cleaned = "".join(ch for ch in cluster if unicodedata.category(ch) not in _SKIP_CATEGORIES)
        if not cleaned:
            continue
        if any(_font_covers(item, cleaned) for item in candidates):
            kept.append(cleaned)
            continue
        for char in cleaned:
            if _is_invisible(char) or char.isspace():
                if kept:
                    kept.append(char)
                continue
            if any(_font_covers(item, char) for item in candidates):
                kept.append(char)
    return "".join(kept)


def _text_width(draw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def _fit(draw, text: str, font, max_width: float, fallback=None) -> str:
    text = "" if text is None else str(text)
    if _text_width_fallback(draw, text, font, fallback) <= max_width:
        return text
    ellipsis = "…"
    clusters = _clusters(text)
    low, high = 0, len(clusters)
    while low < high:
        mid = (low + high + 1) // 2
        if _text_width_fallback(draw, "".join(clusters[:mid]) + ellipsis, font, fallback) <= max_width:
            low = mid
        else:
            high = mid - 1
    return "".join(clusters[:low]) + ellipsis if low else ellipsis


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


def _draw_badge(draw, right: float, center_y: float, text: str, *, replied: bool, size: int = 20):
    font = _font(size)
    width = _text_width(draw, text, font) + 20
    height = size + 14
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
    draw.text((WIDTH / 2, 20), title, font=_font(50, bold=True), fill=TITLE, anchor="ma")
    draw.text(
        (WIDTH / 2, 94),
        f"{period} · 数据更新至 {updated or '-'}",
        font=_font(22),
        fill=SUBTITLE,
        anchor="ma",
    )
    y = 130
    if filter_text:
        draw.text((WIDTH / 2, y), f"筛选：{filter_text}", font=_font(20), fill=FAINT, anchor="ma")
        y += 32
    return y + 16


def _section_title(draw, top: int, title: str, hint: str) -> int:
    x = PAD + SECTION_PAD
    draw.rounded_rectangle([x, top + 4, x + 5, top + 38], radius=2, fill=(139, 108, 201))
    draw.text((x + 14, top), title, font=_font(32, bold=True), fill=TITLE, anchor="la")
    if hint:
        draw.text((WIDTH - PAD - SECTION_PAD, top + 12), hint, font=_font(20), fill=FAINT, anchor="ra")
    return top + 70


def _new_canvas(height: int):
    Image, ImageDraw, _ = _pil()
    image = Image.new("RGB", (WIDTH * SCALE, height * SCALE), BG)
    return image, _ScaledDraw(ImageDraw.Draw(image), SCALE)


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
        font=_font(14),
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
    """逐条时间线（最新在前，按天分组，单栏）。"""
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

    day_gap = 16
    day_header_h = 50
    row_h = 46
    content_height = (
        sum(day_header_h + len(block) * row_h for _, block in day_blocks)
        + day_gap * len(day_blocks)
    )

    section_top = _header_height(filter_text)
    content_top = section_top + 76
    section_bottom = content_top + content_height + 10
    height = section_bottom + 42
    _check_export_size(height)
    image, draw = _new_canvas(height)
    _draw_header(draw, "房间礼物 · 时间线", period, filter_text, updated)
    draw.rounded_rectangle(
        [PAD, section_top, WIDTH - PAD, section_bottom], radius=RADIUS, fill=SECTION_BG
    )
    _section_title(draw, section_top + 14, "送礼时间线", "红＝待回，绿＝已回；最新在前")

    week = "一二三四五六日"
    x0 = PAD + SECTION_PAD
    right = WIDTH - PAD - SECTION_PAD
    time_font = _font(20)
    sender_font = _font(24, bold=True)
    gift_font = _font(24)
    count_font = _font(24, bold=True)

    y = content_top
    for day, block in day_blocks:
        try:
            weekday = week[dt.datetime.strptime(day, "%Y-%m-%d").weekday()]
        except ValueError:
            weekday = ""
        draw.text(
            (x0, y + 4),
            f"{int(day[5:7])}月{int(day[8:10])}日 周{weekday}",
            font=_font(27, bold=True),
            fill=TITLE,
            anchor="la",
        )
        draw.text((right, y + 10), f"{len(block)} 次", font=_font(18), fill=FAINT, anchor="ra")
        draw.line([x0, y + 44, right, y + 44], fill=LINE, width=2)
        y += day_header_h

        for row in block:
            center_y = y + row_h / 2
            replied = _is_replied(row)
            time_text = _fmt_time(str(row.get("gift_bj_time") or ""), with_date=False)
            draw.text((x0, center_y), time_text, font=time_font, fill=FAINT, anchor="lm")
            sender_x = x0 + 90
            sender_max = 320
            sender_fallback = _fallback_for(sender_font)
            sender_text = _fit(
                draw,
                _display_text(row.get("sender_name") or "未知用户", sender_font, sender_fallback),
                sender_font,
                sender_max,
                sender_fallback,
            )
            _draw_text_fallback(
                draw,
                (sender_x, center_y),
                sender_text,
                sender_font,
                sender_fallback,
                fill=NAME if not replied else MUTED,
                anchor="lm",
            )
            gift_x = sender_x + sender_max + 14
            badge_w = 70
            count = _count(row)
            count_text = f"×{count}" if count > 1 else ""
            count_w = _text_width(draw, count_text, count_font) + 8 if count_text else 0
            gift_max = right - badge_w - 10 - count_w - 8 - gift_x
            gift_text = _fit(draw, _display_text(row.get("gift_name") or "-", gift_font), gift_font, max(80, gift_max))
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
            draw.line([x0, y + row_h - 1, right, y + row_h - 1], fill=(240, 232, 245), width=1)
            y += row_h

        y += day_gap

    _footer(draw, height)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _header_height(filter_text: str) -> int:
    return 176 if filter_text else 146


def _card_height(items: list[dict[str, Any]]) -> int:
    return 60 + len(items) * 43


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
    content_top = section_top + 76
    section_bottom = content_top + max(column_heights) + 10
    height = section_bottom + 42
    _check_export_size(height)
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
    _section_title(draw, section_top + 14, "按送礼人汇总", "红＝待回，绿＝已回；按最新送礼时间排")

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
            name_font = _font(28, bold=True)
            name_fallback = _fallback_for(name_font)
            name = _fit(
                draw,
                _display_text(group.get("sender_name") or "未知用户", name_font, name_fallback),
                name_font,
                card_width - 28,
                name_fallback,
            )
            _draw_text_fallback(draw, (x + 14, y + 8), name, name_font, name_fallback, fill=NAME, anchor="la")
            row_y = y + 52
            time_font = _font(20)
            gift_font = _font(24)
            count_font = _font(24, bold=True)
            for row in items:
                center_y = row_y + 21
                replied = _is_replied(row)
                time_text = _fmt_time(str(row.get("gift_bj_time") or ""), with_date=True)
                draw.text((x + 14, center_y), time_text, font=time_font, fill=FAINT, anchor="lm")
                gift_x = x + 14 + 112 + 10
                right = x + card_width - 14
                count = _count(row)
                count_text = f"×{count}" if count > 1 else ""
                count_width = _text_width(draw, count_text, count_font) + 8 if count_text else 0
                badge_width = 70
                gift_max = right - badge_width - 8 - count_width - 8 - gift_x
                gift_text = _fit(draw, _display_text(row.get("gift_name") or "-", gift_font), gift_font, max(50, gift_max))
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
                row_y += 43
            y += card_h + 12

    _footer(draw, height)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
